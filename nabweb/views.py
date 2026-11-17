import abc
import asyncio
import base64
import datetime
import json
import os
import platform
import re

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import translation
from django.utils.translation import to_language, to_locale
from django.views.generic import View

from nabcommon import hardware, update
from nabcommon.nabservice import NabService
from nabd.i18n import Config


class NabdConnection:
    async def __aenter__(self):
        conn = asyncio.open_connection(NabService.HOST, NabService.PORT_NUMBER)
        self.reader, self.writer = await asyncio.wait_for(conn, 0.5)
        return self

    async def __aexit__(self, type, value, traceback):
        self.writer.close()

    @staticmethod
    async def transaction(fun, *args):
        try:
            async with NabdConnection() as conn:
                return await fun(conn.reader, conn.writer, *args)
        except ConnectionRefusedError:
            return {"status": "error", "message": "Nabd is not running."}
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": "Communication with Nabd timed out.",
            }


class BaseView(View, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def template_name(self):
        pass

    async def query_gestalt(self):
        return await NabdConnection.transaction(self._do_query_gestalt)

    async def _do_query_gestalt(self, reader, writer):
        writer.write(b'{"type":"gestalt","request_id":"gestalt"}\r\n')
        await writer.drain()
        while True:
            line = await asyncio.wait_for(reader.readline(), 0.5)
            packet = json.loads(line.decode("utf8"))
            if (
                "type" in packet
                and packet["type"] == "response"
                and "request_id" in packet
                and packet["request_id"] == "gestalt"
            ):
                return {"status": "ok", "result": packet}

    def get_locales(self):
        config = Config.load()
        return [
            (to_locale(lang), name, to_locale(lang) == config.locale)
            for (lang, name) in settings.LANGUAGES
        ]

    def get_context(self):
        user_locale = Config.load().locale
        locales = self.get_locales()
        return {"current_locale": user_locale, "locales": locales}

    def get(self, request, *args, **kwargs):
        context = self.get_context()
        return render(request, self.template_name(), context=context)

    @staticmethod
    def get_services(page):
        services = []
        for config in apps.get_app_configs():
            if hasattr(config.module, "NABAZTAG_SERVICE_PRIORITY"):
                service_page = "services"
                if hasattr(config.module, "NABAZTAG_SERVICE_PAGE"):
                    service_page = config.module.NABAZTAG_SERVICE_PAGE
                if service_page == page:
                    services.append(
                        {
                            "priority": (
                                config.module.NABAZTAG_SERVICE_PRIORITY
                            ),
                            "name": config.name,
                        }
                    )
        services_sorted = sorted(services, key=lambda s: s["priority"])
        services_names = [s["name"] for s in services_sorted]
        return services_names


class NabWebView(BaseView):
    def template_name(self):
        return "nabweb/index.html"

    def get_context(self):
        context = super().get_context()
        context["services"] = BaseView.get_services("home")
        return context

    def post(self, request, *args, **kwargs):
        if "locale" in request.POST:
            config = Config.load()
            config.locale = request.POST["locale"]
            config.save()
            asyncio.run(self.notify_config_update("nabd", "locale"))
            user_language = to_language(config.locale)
            translation.activate(user_language)
            request.LANGUAGE_CODE = translation.get_language()
        context = self.get_context()
        return render(request, self.template_name(), context=context)

    async def notify_config_update(self, service, slot):
        await NabdConnection.transaction(
            self._do_notify_config_update, service, slot
        )

    async def _do_notify_config_update(self, reader, writer, service, slot):
        try:
            packet = (
                f'{{"type":"config-update","service":"{service}",'
                f'"slot":"{slot}"}}\r\n'
            )
            writer.write(packet.encode("utf-8"))
            await writer.drain()
            writer.close()
        except Exception:
            pass


class NabWebServicesView(BaseView):
    def template_name(self):
        return "nabweb/services/index.html"

    def get_context(self):
        context = super().get_context()
        context["services"] = BaseView.get_services("services")
        return context


class NabWebRfidView(BaseView):
    def template_name(self):
        return "nabweb/rfid/index.html"

    @staticmethod
    def get_rfid_services():
        services = []
        for config in apps.get_app_configs():
            if hasattr(config.module, "NABAZTAG_SERVICE_PRIORITY"):
                if hasattr(config.module, "NABAZTAG_RFID_APPLICATION_NAME"):
                    if config.module.NABAZTAG_RFID_APPLICATION_NAME:
                        app_name = config.module.NABAZTAG_RFID_APPLICATION_NAME
                        services.append({"app": config.name, "name": app_name})
        services_sorted = sorted(services, key=lambda s: s["name"])
        return services_sorted

    def get_context(self):
        context = super().get_context()
        gestalt = asyncio.run(self.query_gestalt())
        if gestalt["status"] == "ok":
            rfid = {
                "status": "ok",
                "available": gestalt["result"]["hardware"]["rfid"],
            }
        else:
            rfid = gestalt
        context["rfid_support"] = rfid
        context["rfid_services"] = NabWebRfidView.get_rfid_services()
        return context


async def check_is_idle_state(reader):
    line = await asyncio.wait_for(reader.readline(), 1.0)
    packet = json.loads(line.decode("utf8"))
    if (
        "type" not in packet
        or packet["type"] != "state"
        or "state" not in packet
    ):
        return False, {
            "status": "error",
            "message": "Expected state packet",
        }
    if packet["state"] != "idle":
        return False, {
            "status": "error",
            "message": f"Nabaztag is busy ({packet['state']})",
        }
    return True, None


class NabWebRfidReadView(View):
    READ_TIMEOUT = 30.0

    async def read_tag(self, timeout):
        return await NabdConnection.transaction(self._do_read_tag, timeout)

    async def _do_read_tag(self, reader, writer, timeout):
        is_idle, error_msg = await check_is_idle_state(reader)
        if not is_idle:
            return error_msg
        # Enter interactive mode to get every rfid event (instead of apps)
        packet = (
            '{"type":"mode","mode":"interactive","events":["rfid/*"],'
            '"request_id":"mode"}\r\n'
        )
        writer.write(packet.encode("utf8"))
        await writer.drain()
        while True:
            line = await asyncio.wait_for(reader.readline(), 1.0)
            packet = json.loads(line.decode("utf8"))
            if (
                "type" in packet
                and packet["type"] == "response"
                and "request_id" in packet
                and packet["request_id"] == "mode"
            ):
                # Turn nose red to mean we're expecting a tag now
                base64chor = base64.b64encode(
                    bytes([0, 7, 4, 255, 0, 0, 0, 0])
                )
                packet = (
                    b'{"type":"command","sequence":['
                    b'{"choreography":'
                    b'"data:application/x-nabaztag-mtl-choreography;base64,'
                    + base64chor
                    + b'"}]}\r\n'
                )
                writer.write(packet)
                await writer.drain()
                try:
                    while True:
                        line = await asyncio.wait_for(
                            reader.readline(), timeout
                        )
                        packet = json.loads(line.decode("utf8"))
                        if (
                            "type" in packet
                            and packet["type"] == "rfid_event"
                            and packet["event"] != "removed"
                        ):
                            return {"status": "ok", "event": packet}
                except asyncio.TimeoutError:
                    return {
                        "status": "timeout",
                        "message": "No RFID tag was detected.",
                    }

    def post(self, request, *args, **kwargs):
        read_result = asyncio.run(
            self.read_tag(NabWebRfidReadView.READ_TIMEOUT)
        )
        return JsonResponse(read_result)


class NabWebRfidWriteView(View):
    WRITE_TIMEOUT = 30.0

    async def write_tag(self, tech, uid, picture, app, data, timeout):
        return await NabdConnection.transaction(
            self._do_write_tag, tech, uid, picture, app, data, timeout
        )

    async def _do_write_tag(
        self, reader, writer, tech, uid, picture, app, data, timeout
    ):
        is_idle, error_msg = await check_is_idle_state(reader)
        if not is_idle:
            return error_msg
        packet = {
            "type": "rfid_write",
            "tech": tech,
            "uid": uid,
            "picture": int(picture),
            "app": app,
            "data": data,
            "request_id": "rfid_write",
        }
        packet_json = json.JSONEncoder().encode(packet)
        packet = packet_json + "\r\n"
        writer.write(packet.encode("utf8"))
        await writer.drain()
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout)
                packet = json.loads(line.decode("utf8"))
                if (
                    "type" in packet
                    and packet["type"] == "response"
                    and "request_id" in packet
                    and packet["request_id"] == "rfid_write"
                ):
                    response = {
                        "status": packet["status"],
                        "rfid": {
                            "tech": tech,
                            "uid": uid,
                            "picture": picture,
                            "app": app,
                            "data": data,
                        },
                    }
                    if "message" in packet:
                        response["message"] = packet["message"]
                    return response
            except asyncio.TimeoutError:
                return {
                    "status": "timeout",
                    "message": "No RFID tag was detected.",
                }

    def post(self, request, *args, **kwargs):
        if (
            "tech" not in request.POST
            or "uid" not in request.POST
            or "picture" not in request.POST
            or "app" not in request.POST
        ):
            return JsonResponse(
                {"status": "error", "message": "Missing arguments."},
                status=400,
            )
        tech = request.POST["tech"]
        uid = request.POST["uid"]
        picture = request.POST["picture"]
        app = request.POST["app"]
        if "data" in request.POST:
            data = request.POST["data"]
        else:
            data = ""
        write_result = asyncio.run(
            self.write_tag(
                tech, uid, picture, app, data, NabWebRfidReadView.READ_TIMEOUT
            )
        )
        return JsonResponse(write_result)


class NabWebSytemInfoView(BaseView):
    def template_name(self):
        return "nabweb/system-info/index.html"

    def get_os_info(self):
        version = "(Unknown)"
        if os.path.isdir("/boot/dietpi"):
            variant = "DietPi"
        elif os.path.isfile("/etc/rpi-issue"):
            variant = "Raspberry Pi"
        else:
            variant = ""
        try:
            with open("/etc/os-release") as release_f:
                line = release_f.readline()
                matchObj = re.match(r'PRETTY_NAME="(.+)"$', line, re.M)
                if matchObj:
                    version = matchObj.group(1)
        except FileNotFoundError:
            pass
        kernel_release = platform.release()
        kernel_build = platform.version()
        kernel_machine = platform.machine()
        matchObj = re.match(r"#[0-9]+", kernel_build)
        if matchObj:
            kernel_build = matchObj.group()
        version = (
            f"{version} - "
            f"Kernel {kernel_release} {kernel_build} {kernel_machine}"
        )
        hostname = os.popen("hostname").read().rstrip()
        ip_address = os.popen("hostname -I").read().rstrip()
        wifi_essid = os.popen("iwgetid -r").read().rstrip()
        try:
            with open("/proc/uptime", "r") as uptime_f:
                uptime = int(float(uptime_f.readline().split()[0]))
        except FileNotFoundError:
            uptime = 0
        ssh_state = os.popen("systemctl is-active dropbear").read().rstrip()
        if ssh_state == "inactive":
            ssh_state = os.popen("systemctl is-active ssh").read().rstrip()
        if ssh_state == "active" and os.path.isfile("/run/sshwarn"):
            ssh_state = "sshwarn"
        return {
            "variant": variant,
            "version": version,
            "hostname": hostname,
            "address": ip_address,
            "network": wifi_essid,
            "uptime": uptime,
            "ssh": ssh_state,
        }

    def get_pi_info(self):
        model = hardware.device_model()
        return {"model": model}

    def get_context(self):
        context = super().get_context()
        gestalt = asyncio.run(self.query_gestalt())
        context["gestalt"] = gestalt
        context["os"] = self.get_os_info()
        context["pi"] = self.get_pi_info()
        return context


class NabWebHardwareTestView(View):
    TEST_TIMEOUT = 30.0

    async def hardware_test(self, test, timeout):
        return await NabdConnection.transaction(
            self._do_hardware_test, test, timeout
        )

    async def _do_hardware_test(self, reader, writer, test, timeout):
        try:
            packet = (
                f'{{"type":"test","test":"{test}","request_id":"test"}}\r\n'
            )
            writer.write(packet.encode("utf8"))
            await writer.drain()
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout)
                packet = json.loads(line.decode("utf8"))
                if (
                    "type" in packet
                    and packet["type"] == "response"
                    and "request_id" in packet
                    and packet["request_id"] == "test"
                ):
                    return {"status": "ok", "result": packet}
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": "Communication with Nabd timed out (running test).",
            }

    def post(self, request, *args, **kwargs):
        test = kwargs.get("test")
        test_result = asyncio.run(
            self.hardware_test(test, NabWebHardwareTestView.TEST_TIMEOUT)
        )
        return JsonResponse(test_result)


class GitInfo:
    REPOSITORIES = {"pynab": "."}
    NAMES = {"pynab": "Pynab Trixie"}

    @staticmethod
    def get_root_dir():
        return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

    @staticmethod
    def get_repository_info(repository, cached=False, force=False):
        if repository not in GitInfo.REPOSITORIES:
            raise Http404("Unknown update repository")
        cache_key = f"git/info/{repository}"
        if not force:
            info = cache.get(cache_key)
            if info is not None:
                return info
        if cached:
            return None
        info = GitInfo.do_get_repository_info(repository, ".")
        cache.set(cache_key, info, 60)
        return info

    @staticmethod
    def do_get_repository_info(repository, relpath):
        info = {
            "name": GitInfo.NAMES[repository],
            "info_date": datetime.datetime.now(),
            "url": update.REPOSITORY_URL,
            "tracks_expected_upstream": False,
            "updatable": False,
        }
        try:
            info.update(update.Repository(GitInfo.get_root_dir()).inspect())
            info["updatable"] = info["commits_count"] > 0
        except (OSError, update.UpdateError) as error:
            info.update(status="error", message=str(error))
        return info


class NabWebUpgradeView(BaseView):
    def template_name(self):
        return "nabweb/upgrade/index.html"

    def get_context(self):
        context = super().get_context()
        info = GitInfo.get_repository_info("pynab")
        context.update(
            pynab=info,
            updatable=info["updatable"],
            last_check=info["info_date"],
            update_state=update.read_status(),
        )
        return context


class NabWebUpgradeRepositoryInfoView(View):
    def get(self, request, *args, **kwargs):
        info = GitInfo.get_repository_info(kwargs.get("repository"))
        return render(
            request,
            "nabweb/upgrade/_repository.html",
            context={"repo": info, "updatable": info["updatable"]},
        )


class NabWebUpgradeCheckNowView(View):
    def post(self, request, *args, **kwargs):
        info = GitInfo.get_repository_info("pynab", force=True)
        return JsonResponse({"status": info["status"]})


class NabWebUpgradeStatusView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse(GitInfo.get_repository_info("pynab"))


class NabWebUpgradeNowView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse(update.read_status())

    def post(self, request, *args, **kwargs):
        try:
            update.start_upgrade(GitInfo.get_root_dir())
        except (OSError, update.UpdateError) as error:
            return JsonResponse(
                {"status": "error", "message": str(error)},
                status=409,
            )
        cache.delete("git/info/pynab")
        return JsonResponse({"status": "ok"})


class NabWebShutdownView(View):
    SHUTDOWN_TIMEOUT = 30.0

    async def os_shutdown(self, mode):
        return await NabdConnection.transaction(self._do_os_shutdown, mode)

    async def _do_os_shutdown(self, reader, writer, mode):
        try:
            packet = (
                f'{{"type":"shutdown","mode":"{mode}",'
                f'"request_id":"shutdown"}}\r\n'
            )
            writer.write(packet.encode("utf8"))
            await writer.drain()
            while True:
                line = await asyncio.wait_for(
                    reader.readline(), NabWebShutdownView.SHUTDOWN_TIMEOUT
                )
                packet = json.loads(line.decode("utf8"))
                if (
                    "type" in packet
                    and packet["type"] == "response"
                    and "request_id" in packet
                    and packet["request_id"] == "shutdown"
                ):
                    return {"status": "ok", "result": packet}
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": "Communication with Nabd timed out (shutdown).",
            }

    def post(self, request, *args, **kwargs):
        mode = kwargs.get("mode")
        shutdown_result = asyncio.run(self.os_shutdown(mode))
        return JsonResponse(shutdown_result)

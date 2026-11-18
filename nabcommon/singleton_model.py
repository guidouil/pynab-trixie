from asgiref.sync import sync_to_async
from django.db import connections, models


def _with_transient_connection(operation, /, *args, **kwargs):
    # Daemons have no request lifecycle. Leave connections owned by callers open.
    open_aliases = {
        conn.alias
        for conn in connections.all(initialized_only=True)
        if conn.connection is not None
    }
    try:
        return operation(*args, **kwargs)
    finally:
        for conn in connections.all(initialized_only=True):
            if (
                conn.alias not in open_aliases
                and conn.connection is not None
                and conn.settings_dict["CONN_MAX_AGE"] == 0
                and not conn.in_atomic_block
                and conn.get_autocommit()
            ):
                conn.close()


class SingletonModel(models.Model):
    """
    Singleton model for Django, used for service settings.

    Taken directly from
    https://steelkiwi.com/blog/practical-application-singleton-design-pattern/

    Copyright © 2017 SteelKiwi, http://steelkiwi.com

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super(SingletonModel, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def load_once(cls):
        return _with_transient_connection(cls.load)

    @classmethod
    async def load_async(cls):
        return await sync_to_async(cls.load_once, thread_sensitive=True)()

    async def save_async(self, *args, **kwargs):
        return await sync_to_async(
            _with_transient_connection, thread_sensitive=True
        )(self.save, *args, **kwargs)

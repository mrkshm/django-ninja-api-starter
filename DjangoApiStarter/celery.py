import os

from celery import Celery
from celery.signals import before_task_publish, task_postrun, task_prerun

from core.utils.logging import request_id_context

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "DjangoApiStarter.settings.production",
)

# Create the Celery app
app = Celery("DjangoApiStarter")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@before_task_publish.connect
def add_request_id_header(headers=None, **kwargs):
    request_id = request_id_context.get()
    if request_id and headers is not None:
        headers["request_id"] = request_id


@task_prerun.connect
def bind_task_request_id(task=None, **kwargs):
    request_id = getattr(getattr(task, "request", None), "request_id", None)
    request_id_context.set(request_id)


@task_postrun.connect
def clear_task_request_id(**kwargs):
    request_id_context.set(None)

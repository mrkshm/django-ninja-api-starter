import mimetypes

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404, StreamingHttpResponse

CHUNK_SIZE = 64 * 1024


def media_serve(request, key: str):
    """
    Optional local/dev storage proxy.

    Private production images should be fetched through signed URL endpoints,
    not by stable unauthenticated storage keys.
    """
    if not getattr(settings, "ALLOW_UNAUTHENTICATED_MEDIA_SERVE", False):
        raise Http404()

    try:
        f = default_storage.open(key, mode="rb")
    except Exception:
        raise Http404()

    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"

    def file_iterator():
        try:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                f.close()
            except Exception:
                pass

    resp = StreamingHttpResponse(file_iterator(), content_type=content_type)
    resp["Cache-Control"] = "private, max-age=300"
    return resp

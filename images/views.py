from django.http import StreamingHttpResponse, Http404
from django.core.files.storage import default_storage
import mimetypes


CHUNK_SIZE = 64 * 1024


def media_serve(request, key: str):
    """
    Stream a file from the configured storage by key using a stable URL.
    Example: /media/img_abc123_thumb.webp

    This avoids exposing short-lived presigned URLs to the client.
    """
    # Optional: add authz checks here if needed (e.g., org membership)
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
    # Long-lived immutable cache since variant keys are content-addressed by name
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

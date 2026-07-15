from images.api import access as _access  # noqa: F401
from images.api import deletion as _deletion  # noqa: F401
from images.api import listing as _listing  # noqa: F401
from images.api import metadata as _metadata  # noqa: F401
from images.api import ordering as _ordering  # noqa: F401
from images.api import relations as _relations  # noqa: F401
from images.api import uploads as _uploads  # noqa: F401
from images.api.common import router

__all__ = ["router"]

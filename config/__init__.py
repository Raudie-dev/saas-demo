# Config package
import sys

# Python 3.14+ compatibility patch for Django template context copying in tests
if sys.version_info >= (3, 14):
    try:
        from django.template import context as _d_ctx
        def _base_context_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            duplicate.__dict__.update(self.__dict__)
            duplicate.dicts = self.dicts[:]
            return duplicate
        _d_ctx.BaseContext.__copy__ = _base_context_copy
    except Exception:
        pass

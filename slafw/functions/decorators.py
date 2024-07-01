def safe_call(default_value, exceptions):
    """
    Decorate method to be safe to call

    Wraps method call in try-cache block, cache exceptions and in case of troubles log exception and return
    safe default value.

    :param default_value: Value to return if wrapped function fails
    :param exceptions: Exceptions to catch
    :return: Decorator
    """

    def decor(method):
        def func(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except exceptions:
                self.logger.exception(f"Call to {method.__name__} failed, returning safe default")
                return default_value

        return func

    return decor

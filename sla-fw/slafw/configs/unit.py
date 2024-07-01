import operator


class Unit:
    def __init__(self, val: int):
        self._val = int(val)

    @property
    def val(self):
        return self._val

    def __str__(self):
        return str(self.val)

    def __int__(self):
        return int(self.val)

    def __float__(self):
        return float(self.val)

    def __repr__(self):
        return repr(self.val)

    def __bool__(self):
        return bool(self.val)

    def __add__(self, other):
        return self._int_not_compatible(other, operator.add)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        return self._int_not_compatible(other, operator.sub)

    def __rsub__(self, other):
        return self.__sub__(other)

    def __mul__(self, other):
        return self._int_compatible(other, operator.mul)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __floordiv__(self, other):
        return self._int_compatible(other, operator.floordiv)

    def __rfloordiv__(self, other):
        return self.__floordiv__(other)

    def __mod__(self, other):
        return self._int_compatible(other, operator.mod)

    def __rmod__(self, other):
        return self.__mod__(other)

    def __truediv__(self, other):
        return self._int_compatible(other, operator.truediv)

    def __rtruediv__(self, other):
        return self.__truediv__(other)

    def __neg__(self):
        return self.__class__(-self.val)

    def __eq__(self, other):
        return self._int_not_compatible(other, operator.eq, return_bool=True)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __gt__(self, other):
        return self._int_not_compatible(other, operator.gt, return_bool=True)

    def __lt__(self, other):
        return self._int_not_compatible(other, operator.lt, return_bool=True)

    def __le__(self, other):
        return self._int_not_compatible(other, operator.le, return_bool=True)

    def __ge__(self, other):
        return self._int_not_compatible(other, operator.ge, return_bool=True)

    def __abs__(self):
        return self.__class__(operator.abs(self.val))

    def _int_compatible(self, other, operation):
        if isinstance(other, self.__class__):
            return self.__class__(operation(self.val, other.val))
        if isinstance(other, int):
            return self.__class__(operation(self.val, other))
        raise TypeError(f"Units {self.__class__} and {other.__class__} are incompatible")

    def _int_not_compatible(self, other, operation, return_bool=False):
        if return_bool and other is None:
            return self.val is None
        return_obj = self.__class__
        if return_bool:
            return_obj = bool
        if isinstance(other, self.__class__):
            return return_obj(operation(self.val, other.val))
        raise TypeError(f"Units {self.__class__} and {other.__class__} are incompatible")


class Nm(Unit):
    # pylint: disable=too-few-public-methods
    pass


class Ustep(Unit):
    # pylint: disable=too-few-public-methods
    pass

class Ms(Unit):
    # pylint: disable=too-few-public-methods
    pass

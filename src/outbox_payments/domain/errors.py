"""Domain errors: violations of business invariants, independent of any transport."""


class DomainError(Exception):
    """Base class for every business-rule violation."""


class InvalidMoneyError(DomainError):
    """The amount cannot represent a payable sum."""


class InvalidStatusTransitionError(DomainError):
    """A payment was asked to move to a status its state machine does not allow."""

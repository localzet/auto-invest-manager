class ExecutionPlanningError(Exception):
    """Raised when an execution plan violates structural invariants."""


class RiskRejectedError(Exception):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))

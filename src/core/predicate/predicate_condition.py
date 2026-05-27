from dataclasses import dataclass, field


@dataclass
class predicate_condition:
    _condition : str = field(init=True, default="")
    _monotone : bool = field(init=True, default=False)


    def condition(self) -> str:
        return self._condition
    
    def is_monotone(self) -> bool:
        return self._monotone
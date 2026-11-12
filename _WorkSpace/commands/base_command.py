from abc import ABC, abstractmethod
from typing import List, Callable


class ICommand(ABC):
    @abstractmethod
    def execute(self) -> None:
        pass

    @abstractmethod
    def undo(self) -> None:
        pass

    @property
    def description(self) -> str:
        return self.__class__.__name__


class CommandManager:
    def __init__(self) -> None:
        self._undo_stack: List[ICommand] = []
        self._redo_stack: List[ICommand] = []
        self._listeners: List[Callable[[], None]] = []

    def add_change_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in self._listeners:
            callback()

    def execute_command(self, command: ICommand) -> None:
        command.execute()
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._notify()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        if not self.can_undo():
            return False
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self.can_redo():
            return False
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        self._notify()
        return True

    def clear(self, notify: bool = False) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        if notify:
            self._notify()

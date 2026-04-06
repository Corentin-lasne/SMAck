from dataclasses import dataclass


@dataclass
class Message:
    """Simple message exchanged between robot agents."""

    sender_id: int
    recipient_id: int
    performative: str
    content: dict


class Mailbox:
    """Mailbox with unread/read message tracking."""

    def __init__(self):
        self._unread_messages = []
        self._read_messages = []

    def receive_message(self, message):
        self._unread_messages.append(message)

    def pop_new_messages(self):
        new_messages = self._unread_messages.copy()
        self._read_messages.extend(new_messages)
        self._unread_messages.clear()
        return new_messages

    def get_all_messages(self):
        if self._unread_messages:
            self.pop_new_messages()
        return self._read_messages.copy()
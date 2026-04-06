"""Red agent policy variants."""

from .base import BasePolicy, deliberate_red_no_communication, deliberate_red_with_communication, handle_standard_message


class RedNoCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        return deliberate_red_no_communication(agent)


class RedWidespreadCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        return deliberate_red_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)
"""Yellow agent policy variants."""

from .base import BasePolicy, deliberate_yellow_no_communication, deliberate_yellow_with_communication, handle_standard_message


class YellowNoCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        return deliberate_yellow_no_communication(agent)

class YellowWidespreadCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        return deliberate_yellow_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)

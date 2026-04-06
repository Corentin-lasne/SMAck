"""Green agent policy variants."""

from .base import BasePolicy, deliberate_green_no_communication, deliberate_green_with_communication, handle_standard_message


class GreenNoCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = False
        return deliberate_green_no_communication(agent)

class GreenWidespreadCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = False
        return deliberate_green_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)


class GreenWidespreadCommunicationSmartExploPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = True
        return deliberate_green_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)

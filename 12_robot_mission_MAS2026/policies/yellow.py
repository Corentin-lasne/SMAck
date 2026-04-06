"""Yellow agent policy variants."""

from .base import BasePolicy, deliberate_yellow_no_communication, deliberate_yellow_with_communication, handle_standard_message


class YellowNoCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = False
        return deliberate_yellow_no_communication(agent)

class YellowWidespreadCommunicationPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = False
        return deliberate_yellow_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)


class YellowWidespreadCommunicationSmartExploPolicy(BasePolicy):
    def deliberate(self, agent):
        agent.smart_exploration_enabled = True
        return deliberate_yellow_with_communication(agent)

    def handle_message(self, agent, message):
        return handle_standard_message(agent, message)

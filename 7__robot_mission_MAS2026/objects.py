from mesa import Agent

import random

class RadioactivityAgent(Agent):
    """ An agent with a radioactivity level. 
    The radioactivity level is a random number between 0 and 1, depending on the zone of the grid.
    If the radioactivity level is 10, then it is the Waste Disposal Zone.
    It has no behaviour.
    """
    def __init__(self, zone, position, model):
        super().__init__(model)
        self.position = position
        if zone == 1 :
            self.radioactivity = random.uniform(0,0.33)
        elif zone == 2 :
            self.radioactivity = random.uniform(0.33,0.66)
        elif zone == 3 :
            self.radioactivity = random.uniform(0.66,1)
        else :
            self.radioactivity = 10

class WasteAgent(Agent):
    """ An agent that represents a waste. 
    It has no behaviour.
    """
    def __init__(self, position, waste_type, model):
        super().__init__(model)
        self.position = position
        self.waste_type = waste_type

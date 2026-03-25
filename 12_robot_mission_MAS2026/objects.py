""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""

from mesa import Agent

import random

class radioactivityAgent(Agent):
    """ An agent with a radioactivity level. 
    The radioactivity level is a random number between 0 and 1, depending on the zone of the grid.
    If the radioactivity level is 10, then it is the Waste Disposal Zone.
    It has no behaviour.
    """
    def __init__(self, model, zone):
        super().__init__(model)
        if zone == 1 :
            self.radioactivity = random.uniform(0,0.33)
        elif zone == 2 :
            self.radioactivity = random.uniform(0.33,0.66)
        elif zone == 3 :
            self.radioactivity = random.uniform(0.66,1)
        # Waste Disposal Zone
        else :
            self.radioactivity = 10

class wasteAgent(Agent):
    """ An agent that represents a waste. 
    It has no behaviour.
    """
    def __init__(self, model, waste_type, waste_id=None):
        super().__init__(model)
        self.waste_type = waste_type
        self.waste_id = waste_id

""" 
Group number: 12
Group members:
    - Tomas Stone
    - Clara Vega
    - Corentin Lasne
Date of creation : 16/03/2026
"""



from mesa import Model
from mesa.space import MultiGrid
from agents import greenAgent, yellowAgent, redAgent
from objects import radioactivityAgent, wasteAgent

class Model(Model):
    """Environment authority for movement, manipulation, communication, and metrics.

    Robot agents choose actions, but this class remains the single source of truth:
    it validates legal actions at execution time and applies state transitions.
    """
    def __init__(self, n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_green_waste=1, n_yellow_waste=0, n_red_waste=0, width=10, height=10, seed=None):
        """Initialize the model.

        Args:
            n_green_agents (int, optional): Number of green agents. Defaults to 1.
            n_yellow_agents (int, optional): Number of yellow agents. Defaults to 1.
            n_red_agents (int, optional): Number of red agents. Defaults to 1.
            n_green_waste (int, optional): Number of green waste items. Defaults to 1.
            n_yellow_waste (int, optional): Number of yellow waste items. Defaults to 0.
            n_red_waste (int, optional): Number of red waste items. Defaults to 0.
            width (int, optional): Grid width. Defaults to 100.
            height (int, optional): Grid height. Defaults to 100.
            seed (int, optional): Random seed. Defaults to None.
        """
        super().__init__(seed=seed)
        self.num_green_agents = n_green_agents
        self.num_yellow_agents = n_yellow_agents
        self.num_red_agents = n_red_agents
        self.num_green_waste = n_green_waste
        self.num_yellow_waste = n_yellow_waste
        self.num_red_waste = n_red_waste
        
        self.grid = MultiGrid(width, height, torus=False)
        self.robotAgents = []
        self.wasteAgents = []
        self.mailboxes = {}
        self.pending_messages = []
        self.query_counter = 0
        self.waste_counter = 0
        self.disposed_red_count = 0
        self.debug = False  # Enable debug logging by setting to True
        
        # Metrics tracking
        self.waste_count_history = []  # [{"step": 0, "green": 1, "yellow": 0, "red": 0, "total": 1}, ...]
        self.cumulative_distance_history = []  # [{"step": 0, "distance": X}, ...]
        self.steps = 0
        
        # Define z1, z2, z3 as third area of the grid
        self.z1 = (0, 0, width//3, height)
        self.z2 = (width//3, 0, 2*width//3, height)
        self.z3 = (2*width//3, 0, width, height)

        # Create the Waste Disposal Zone at the very right of the grid, at random y position
        waste_disposal_zone_y = self.random.randrange(0, height)
        self.waste_disposal_zone = (width-1, waste_disposal_zone_y)
        self.grid.place_agent(radioactivityAgent(self, 4), (width-1, waste_disposal_zone_y))

        # Attribute corresponding radioactivity agents to each area cell
        for x in range(self.z1[0], self.z1[2]):
            for y in range(self.z1[1], self.z1[3]):
                self.grid.place_agent(radioactivityAgent(self, 1), (x, y))
        
        for x in range(self.z2[0], self.z2[2]):
            for y in range(self.z2[1], self.z2[3]):
                self.grid.place_agent(radioactivityAgent(self, 2), (x, y))
        
        for x in range(self.z3[0], self.z3[2]):
            for y in range(self.z3[1], self.z3[3]):
                if (x, y) != (width-1, waste_disposal_zone_y):  # Avoid placing a radioactivity agent on the Waste Disposal Zone
                    self.grid.place_agent(radioactivityAgent(self, 3), (x, y))

        # Create Green waste agents in Z1
        for _ in range(self.num_green_waste):
            x = self.random.randrange(self.z1[0], self.z1[2])
            y = self.random.randrange(self.z1[1], self.z1[3])
            waste = wasteAgent(self, "green")
            self.wasteAgents.append(waste)
            self.grid.place_agent(waste, (x, y))

        # Create Yellow waste agents in Z2
        for _ in range(self.num_yellow_waste):
            x = self.random.randrange(self.z2[0], self.z2[2])
            y = self.random.randrange(self.z2[1], self.z2[3])
            waste = wasteAgent(self, "yellow")
            self.wasteAgents.append(waste)
            self.grid.place_agent(waste, (x, y))

        # Create Red waste agents in Z3
        for _ in range(self.num_red_waste):
            x = self.random.randrange(self.z3[0], self.z3[2])
            y = self.random.randrange(self.z3[1], self.z3[3])
            if (x, y) != self.waste_disposal_zone:
                waste = wasteAgent(self, "red")
                self.wasteAgents.append(waste)
                self.grid.place_agent(waste, (x, y))

        # Create agents and place them randomly in their area
        for _ in range(self.num_green_agents):
            green_agent = greenAgent(self)
            self.robotAgents.append(green_agent)
            pos = self.get_random_free_robot_position(self.z1)
            self.grid.place_agent(green_agent, pos)
            self.mailboxes[green_agent.unique_id] = []
            
        for _ in range(self.num_yellow_agents):
            yellow_agent = yellowAgent(self)
            self.robotAgents.append(yellow_agent)
            pos = self.get_random_free_robot_position(self.z2)
            self.grid.place_agent(yellow_agent, pos)
            self.mailboxes[yellow_agent.unique_id] = []
            
        for _ in range(self.num_red_agents):
            red_agent = redAgent(self)
            self.robotAgents.append(red_agent)
            pos = self.get_random_free_robot_position(self.z3)
            self.grid.place_agent(red_agent, pos)
            self.mailboxes[red_agent.unique_id] = []
        
    def step(self):
        """Advance the simulation by one step using shuffled robot activation."""
        self._deliver_pending_messages()
        agent_list = list(self.robotAgents)
        self.random.shuffle(agent_list)
        for agent in agent_list:
            agent.step_agent()
        
        # Record metrics at the end of each step
        self._record_metrics()

    def make_waste_id(self):
        """Return a unique persistent identifier for each waste token."""
        self.waste_counter += 1
        return f"w-{self.waste_counter}"
    
    def _record_metrics(self):
        """Record waste count and cumulative distance metrics."""
        # Count wastes by type
        green_count = sum(1 for w in self.wasteAgents if w.waste_type == "green")
        yellow_count = sum(1 for w in self.wasteAgents if w.waste_type == "yellow")
        red_count = sum(1 for w in self.wasteAgents if w.waste_type == "red")
        
        # Count wastes in robots' inventories
        for agent in self.robotAgents:
            for waste in agent.inventory:
                if waste.waste_type == "green":
                    green_count += 1
                elif waste.waste_type == "yellow":
                    yellow_count += 1
                elif waste.waste_type == "red":
                    red_count += 1
        
        total_count = green_count + yellow_count + red_count
        
        self.waste_count_history.append({
            "step": self.steps,
            "green": green_count,
            "yellow": yellow_count,
            "red": red_count,
            "total": total_count
        })
        
        # Calculate cumulative distance to disposal zone
        cumulative_distance = 0
        
        # Distance of wastes on the map
        for waste in self.wasteAgents:
            dist = abs(waste.pos[0] - self.waste_disposal_zone[0]) + abs(waste.pos[1] - self.waste_disposal_zone[1])
            cumulative_distance += dist
        
        # Distance of wastes in robots' inventories (use robot position)
        for agent in self.robotAgents:
            for waste in agent.inventory:
                dist = abs(agent.pos[0] - self.waste_disposal_zone[0]) + abs(agent.pos[1] - self.waste_disposal_zone[1])
                cumulative_distance += dist
        
        self.cumulative_distance_history.append({
            "step": self.steps,
            "distance": cumulative_distance
        })

    def is_robot_cell_free(self, pos, moving_agent=None):
        """Return True if no other robot agent is on this cell."""
        cell_contents = self.grid.get_cell_list_contents([pos])
        return not any(obj in self.robotAgents and obj is not moving_agent for obj in cell_contents)

    def get_random_free_robot_position(self, zone):
        """Pick a random position in a zone that is not occupied by another robot."""
        x_min, y_min, x_max, y_max = zone
        max_attempts = self.grid.width * self.grid.height

        for _ in range(max_attempts):
            pos = (
                self.random.randrange(x_min, x_max),
                self.random.randrange(y_min, y_max),
            )
            if self.is_robot_cell_free(pos):
                return pos

        raise RuntimeError("No free position available to place a robot in the selected zone")

    def do(self, agent, action):
        """Environment-side legal validation with random legal fallback for invalid actions."""
        if isinstance(action, dict) and action.get("type") == "send_message":
            message = action.get("message")
            if isinstance(message, dict) and message.get("type"):
                self.send_message(agent, message)
                return self.get_percepts(agent)

        legal_actions = self.get_legal_actions(agent)
        if action not in legal_actions:
            if not legal_actions:
                return self.get_percepts(agent)
            action = self.random.choice(legal_actions)

        if action.startswith("move"):
            direction = action.split("_")[1]
            return self.move_agent(agent, direction)
        if action == "pick_up":
            return self.pick_up(agent)
        if action == "drop":
            return self.drop(agent)
        if action == "transform":
            return self.transform(agent)
        return self.get_percepts(agent)

    def make_query_id(self):
        """Return a unique ID used to match asynchronous request/reply messages."""
        self.query_counter += 1
        return f"q-{self.steps}-{self.query_counter}"

    def _deliver_pending_messages(self):
        """Deliver queued messages at step boundaries (asynchronous mailbox model)."""
        for recipient_id, envelope in self.pending_messages:
            if recipient_id in self.mailboxes:
                self.mailboxes[recipient_id].append(envelope)
        self.pending_messages = []

    def read_messages(self, agent):
        """Return and clear all messages currently available to an agent."""
        messages = self.mailboxes.get(agent.unique_id, [])
        self.mailboxes[agent.unique_id] = []
        return messages

    def send_message(self, sender, message):
        """Queue a direct, role-based, or broadcast message for next-step delivery."""
        envelope = {
            "from": sender.unique_id,
            "type": message.get("type"),
            "payload": message.get("payload", {}),
        }
        
        # DEBUG
        print(f"Agent {sender.unique_id} sends message: {message}")
        direct_target = message.get("to")
        role_target = message.get("to_role")

        recipients = []
        if direct_target is not None:
            recipients = [direct_target]
        elif role_target is not None:
            recipients = [a.unique_id for a in self.robotAgents if getattr(a, "agent_role", None) == role_target and a is not sender]
        else:
            recipients = [a.unique_id for a in self.robotAgents if a is not sender]

        for recipient_id in recipients:
            self.pending_messages.append((recipient_id, envelope))

    def get_legal_actions(self, agent):
        """Compute legal primitive actions from current world state."""
        legal = []
        x, y = agent.pos
        move_targets = {
            "move_up": (x, y + 1),
            "move_down": (x, y - 1),
            "move_right": (x + 1, y),
            "move_left": (x - 1, y),
        }

        for action_name, target_pos in move_targets.items():
            if self.grid.out_of_bounds(target_pos):
                continue
            if not self.is_position_allowed(agent, target_pos):
                continue
            if not self.is_robot_cell_free(target_pos, moving_agent=agent):
                continue
            legal.append(action_name)

        if self._can_pick_up(agent):
            legal.append("pick_up")

        if len(agent.inventory) > 0:
            legal.append("drop")

        if self._can_transform(agent):
            legal.append("transform")

        return legal

    def _can_pick_up(self, agent):
        """Check whether the agent can legally pick up a waste now."""
        if len(agent.inventory) >= agent.max_capacity:
            return False

        target_type = getattr(agent, "target_waste_type", None)
        target_id = None
        task = getattr(agent, "active_task", None)
        if task is not None and not task.get("picked", False):
            task_type = task.get("waste_type")
            if task_type:
                target_type = task_type
            target_id = task.get("waste_id")

        if target_type is None:
            return False

        if not self._is_pickable_type_for_agent(agent, target_type):
            return False

        if self._is_lower_waste_for_agent(agent, target_type) and len(agent.inventory) > 0:
            return False

        cell_contents = self.grid.get_cell_list_contents([agent.pos])
        return any(
            isinstance(obj, wasteAgent)
            and obj.waste_type == target_type
            and (target_id is None or obj.waste_id == target_id)
            for obj in cell_contents
        )

    def _can_transform(self, agent):
        """Check whether the agent inventory satisfies transform preconditions."""
        target = getattr(agent, "target_waste_type", None)
        result = getattr(agent, "result_waste_type", None)
        if result is None or target is None:
            return False
        matching = [w for w in agent.inventory if w.waste_type == target]
        return len(matching) >= 2
        
    def move_agent(self, agent, direction):
        """Move an agent by one cardinal step if bounds/zone/occupancy constraints allow."""
        x, y = agent.pos
        delta = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
        if direction not in delta:
            raise ValueError(f"Unknown direction: {direction}")
        dx, dy = delta[direction]
        new_pos = (x + dx, y + dy)
 
        if self.grid.out_of_bounds(new_pos):
            return self.get_percepts(agent)
        if not self.is_position_allowed(agent, new_pos):
            return self.get_percepts(agent)
        if not self.is_robot_cell_free(new_pos, moving_agent=agent):
            return self.get_percepts(agent)
 
        self.grid.move_agent(agent, new_pos)
        return self.get_percepts(agent)

    def get_zone_name(self, pos):
        """Return the zone name (z1, z2, z3) for a grid position."""
        x, y = pos

        if self.z1[0] <= x < self.z1[2] and self.z1[1] <= y < self.z1[3]:
            return "z1"
        if self.z2[0] <= x < self.z2[2] and self.z2[1] <= y < self.z2[3]:
            return "z2"
        if self.z3[0] <= x < self.z3[2] and self.z3[1] <= y < self.z3[3]:
            return "z3"

        return None

    def is_position_allowed(self, agent, pos):
        """Check whether a position belongs to one of the agent allowed zones."""
        allowed_zones = getattr(agent, "allowed_zones", None)
        if not allowed_zones:
            return True

        zone_name = self.get_zone_name(pos)
        return zone_name in allowed_zones

    def pick_up(self, agent):
        """Transfer one eligible waste from grid cell to agent inventory."""
        target_type = agent.target_waste_type
        target_id = None
        task = getattr(agent, "active_task", None)
        if task is not None and not task.get("picked", False):
            task_target = task.get("waste_type")
            if task_target:
                target_type = task_target
            target_id = task.get("waste_id")

        if not self._is_pickable_type_for_agent(agent, target_type):
            return self.get_percepts(agent)

        if self._is_lower_waste_for_agent(agent, target_type) and len(agent.inventory) > 0:
            return self.get_percepts(agent)

        cell_contents = self.grid.get_cell_list_contents([agent.pos])
        for obj in cell_contents:
            if (
                isinstance(obj, wasteAgent)
                and len(agent.inventory) < agent.max_capacity
                and obj.waste_type == target_type
                and (target_id is None or obj.waste_id == target_id)
            ):
                agent.inventory.append(obj)
                self.grid.remove_agent(obj)
                if obj in self.wasteAgents:
                    self.wasteAgents.remove(obj)
                break
        return self.get_percepts(agent)

    def _is_lower_waste_for_agent(self, agent, waste_type):
        role = getattr(agent, "agent_role", None)
        if role == "yellow":
            return waste_type == "green"
        if role == "red":
            return waste_type in {"green", "yellow"}
        return False

    def _is_pickable_type_for_agent(self, agent, waste_type):
        role = getattr(agent, "agent_role", None)
        if role == "green":
            return waste_type == "green"
        if role == "yellow":
            return waste_type in {"green", "yellow"}
        if role == "red":
            return waste_type in {"green", "yellow", "red"}
        return True

    def drop(self, agent):
        """Drop one carried waste into the current cell or dispose red waste at disposal zone."""
        if agent.inventory:
            waste = agent.inventory.pop()
            if agent.pos == self.waste_disposal_zone:
                # Any waste delivered to the final depot is removed from simulation.
                self.disposed_red_count += 1
            else:
                self.grid.place_agent(waste, agent.pos)
                self.wasteAgents.append(waste)
        return self.get_percepts(agent)

    def transform(self, agent):
        """Consume two target wastes from inventory and produce one upgraded waste."""
        target = agent.target_waste_type
        result = agent.result_waste_type
 
        if result is None:
            return self.get_percepts(agent)
 
        matching = [w for w in agent.inventory if w.waste_type == target]
        if len(matching) < 2:
            return self.get_percepts(agent)  # not enough waste to transform

        else :
            agent.inventory = []
 
        # Produce 1 result waste and place directly in inventory
        new_waste = wasteAgent(self, result)
        agent.inventory.append(new_waste)
 
        return self.get_percepts(agent)
    
    def get_percepts(self, agent):
        """Return local percepts: current position and Moore neighborhood contents."""
        percepts = {"position": agent.pos, "surrounding": {}}
        if agent.pos:
            # Get just the 8 surrounding cells (including diagonals) and the current cell contents
            neighborhood = self.grid.get_neighborhood(agent.pos, include_center=True, moore=True)
            for pos in neighborhood:
                percepts["surrounding"][pos] = self.grid.get_cell_list_contents([pos])
        return percepts
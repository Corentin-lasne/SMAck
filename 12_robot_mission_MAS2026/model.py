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
from config import DEFAULT_MODEL_PARAMS
from messaging import Message, Mailbox

class Model(Model):
    """A model with some number of agents, number of waste, and a grid cell."""
    def __init__(self, n_green_agents=1, n_yellow_agents=1, n_red_agents=1, n_green_waste=1, n_yellow_waste=0, n_red_waste=0, width=10, height=10, seed=None, policy_profile_green=DEFAULT_MODEL_PARAMS["policy_profile_green"], policy_profile_yellow=DEFAULT_MODEL_PARAMS["policy_profile_yellow"], policy_profile_red=DEFAULT_MODEL_PARAMS["policy_profile_red"]):
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
        self.policy_profile_green = policy_profile_green
        self.policy_profile_yellow = policy_profile_yellow
        self.policy_profile_red = policy_profile_red
        
        self.grid = MultiGrid(width, height, torus=False)
        self.robotAgents = []
        self.wasteAgents = []
        self.agent_mailboxes = {}
        self.agent_index_by_id = {}
        self._next_agent_id = 1
        self._next_waste_id = 1
        self._next_query_id = 1
        
        # Metrics tracking
        self.waste_count_history = []  # [{"step": 0, "green": 1, "yellow": 0, "red": 0, "total": 1}, ...]
        self.cumulative_distance_history = []  # [{"step": 0, "distance": X}, ...]
        self.steps = 0
        self.running = True
        self.step_green_zero = None
        self.step_yellow_zero = None
        self.step_red_zero = None
        self.step_total_zero = None
        # Track whether each type has existed at least once in the run.
        # This prevents recording a misleading extinction step at 0 for types
        # that start absent (e.g., yellow/red when initialized at 0).
        self.type_seen_positive = {
            "green": False,
            "yellow": False,
            "red": False,
        }
        self.disposed_counts = {
            "green": 0,
            "yellow": 0,
            "red": 0,
            "total": 0,
        }
        
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
            waste = wasteAgent(self, "green", waste_id=self.next_waste_id())
            self.wasteAgents.append(waste)
            self.grid.place_agent(waste, (x, y))

        # Create Yellow waste agents in Z2
        for _ in range(self.num_yellow_waste):
            x = self.random.randrange(self.z2[0], self.z2[2])
            y = self.random.randrange(self.z2[1], self.z2[3])
            waste = wasteAgent(self, "yellow", waste_id=self.next_waste_id())
            self.wasteAgents.append(waste)
            self.grid.place_agent(waste, (x, y))

        # Create Red waste agents in Z3
        for _ in range(self.num_red_waste):
            x = self.random.randrange(self.z3[0], self.z3[2])
            y = self.random.randrange(self.z3[1], self.z3[3])
            if (x, y) != self.waste_disposal_zone:
                waste = wasteAgent(self, "red", waste_id=self.next_waste_id())
                self.wasteAgents.append(waste)
                self.grid.place_agent(waste, (x, y))

        # Create agents and place them randomly in their area
        for _ in range(self.num_green_agents):
            green_agent = greenAgent(self, agent_id=self.next_agent_id(), policy_profile=self.policy_profile_green)
            self.robotAgents.append(green_agent)
            self._register_robot_mailbox(green_agent)
            pos = self.get_random_free_robot_position(self.z1)
            self.grid.place_agent(green_agent, pos)
            
        for _ in range(self.num_yellow_agents):
            yellow_agent = yellowAgent(self, agent_id=self.next_agent_id(), policy_profile=self.policy_profile_yellow)
            self.robotAgents.append(yellow_agent)
            self._register_robot_mailbox(yellow_agent)
            pos = self.get_random_free_robot_position(self.z2)
            self.grid.place_agent(yellow_agent, pos)
            
        for _ in range(self.num_red_agents):
            red_agent = redAgent(self, agent_id=self.next_agent_id(), policy_profile=self.policy_profile_red)
            self.robotAgents.append(red_agent)
            self._register_robot_mailbox(red_agent)
            pos = self.get_random_free_robot_position(self.z3)
            self.grid.place_agent(red_agent, pos)

        # Initialize extinction trackers for already-zero initial conditions.
        initial_counts = self._compute_waste_counts()
        for waste_type in self.type_seen_positive:
            self.type_seen_positive[waste_type] = initial_counts[waste_type] > 0
        self._update_extinction_steps(initial_counts)
        if initial_counts["total"] == 0:
            self.running = False

    def next_agent_id(self):
        agent_id = self._next_agent_id
        self._next_agent_id += 1
        return agent_id

    def next_waste_id(self):
        waste_id = self._next_waste_id
        self._next_waste_id += 1
        return waste_id

    def next_query_id(self):
        query_id = self._next_query_id
        self._next_query_id += 1
        return query_id
        
    def step(self):
        if not self.running:
            return
        agent_list = list(self.robotAgents)
        self.random.shuffle(agent_list)
        for agent in agent_list:
            agent.step_agent()
        
        # Record metrics at the end of each step
        self._record_metrics()

    def _compute_waste_counts(self):
        """Compute current counts for each waste type including inventories."""
        green_count = sum(1 for w in self.wasteAgents if w.waste_type == "green")
        yellow_count = sum(1 for w in self.wasteAgents if w.waste_type == "yellow")
        red_count = sum(1 for w in self.wasteAgents if w.waste_type == "red")

        for agent in self.robotAgents:
            for waste in agent.inventory:
                if waste.waste_type == "green":
                    green_count += 1
                elif waste.waste_type == "yellow":
                    yellow_count += 1
                elif waste.waste_type == "red":
                    red_count += 1

        return {
            "green": green_count,
            "yellow": yellow_count,
            "red": red_count,
            "total": green_count + yellow_count + red_count,
        }

    def _update_extinction_steps(self, counts):
        """Store the first step where each waste count reaches zero."""
        for waste_type in self.type_seen_positive:
            if counts[waste_type] > 0:
                self.type_seen_positive[waste_type] = True

        if (
            self.step_green_zero is None
            and self.type_seen_positive["green"]
            and counts["green"] == 0
        ):
            self.step_green_zero = self.steps
        if (
            self.step_yellow_zero is None
            and self.type_seen_positive["yellow"]
            and counts["yellow"] == 0
        ):
            self.step_yellow_zero = self.steps
        if (
            self.step_red_zero is None
            and self.type_seen_positive["red"]
            and counts["red"] == 0
        ):
            self.step_red_zero = self.steps
        if self.step_total_zero is None and counts["total"] == 0:
            self.step_total_zero = self.steps
    
    def _record_metrics(self):
        """Record waste count and cumulative distance metrics."""
        counts = self._compute_waste_counts()
        green_count = counts["green"]
        yellow_count = counts["yellow"]
        red_count = counts["red"]
        total_count = counts["total"]
        self._update_extinction_steps(counts)
        
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

        if total_count == 0:
            self.running = False

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
        """Execute the given action for the specified agent and returns the resulting percepts."""
        if action is None:
            # No feasible action this turn (blocked or no valid policy branch).
            return self.get_percepts(agent)

        # Keep agent state stable for a short window after answering a carry query.
        if action in {"pick_up", "drop", "transform"} and agent.current_step < agent.state_change_freeze_until:
            return self.get_percepts(agent)

        if action.startswith("move"):
            direction = action.split("_")[1]
            return self.move_agent(agent, direction)
        elif action == "pick_up":
            return self.pick_up(agent)
        elif action == "drop":
            return self.drop(agent)
        elif action == "transform":
            return self.transform(agent)
        elif action == "send_message":
            return self.send_agent_message(agent)
        else:
            raise ValueError(f"Unknown action: {action}")
        
    def move_agent(self, agent, direction):
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
        """Pick up waste if the agent is on a cell with waste and return the resulting percepts."""
        cell_contents = self.grid.get_cell_list_contents([agent.pos])
        for obj in cell_contents:
            if isinstance(obj, wasteAgent) and agent._can_add_waste_type(obj.waste_type, obj.waste_id, obj.pos):
                agent.inventory.append(obj)
                self.grid.remove_agent(obj)
                if obj in self.wasteAgents:
                    self.wasteAgents.remove(obj)
                break
        return self.get_percepts(agent)

    def drop(self, agent):
        """Drop waste if the agent is carrying waste and return the resulting percepts."""
        if agent.inventory:
            waste = agent.inventory.pop()
            agent.last_dropped_waste_id = waste.waste_id
            agent.last_dropped_waste_type = waste.waste_type
            agent.last_dropped_waste_pos = agent.pos
            if agent.pos == self.waste_disposal_zone:
                # Disposed!
                self.disposed_counts[waste.waste_type] += 1
                self.disposed_counts["total"] += 1
            else:
                self.grid.place_agent(waste, agent.pos)
                self.wasteAgents.append(waste)
        return self.get_percepts(agent)

    def transform(self, agent):
        """Transform waste if the agent has the required wastes and return the resulting percepts."""
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
        new_waste = wasteAgent(self, result, waste_id=self.next_waste_id())
        agent.inventory.append(new_waste)
 
        return self.get_percepts(agent)
    
    def get_percepts(self, agent):
        """Get percepts for an agent (its current position and surroundings)."""
        percepts = {"position": agent.pos, "surrounding": {}}
        if agent.pos:
            # Get just the 8 surrounding cells (including diagonals) and the current cell contents
            neighborhood = self.grid.get_neighborhood(agent.pos, include_center=True, moore=True)
            for pos in neighborhood:
                percepts["surrounding"][pos] = self.grid.get_cell_list_contents([pos])
        return percepts
    
    
 # ================================
 ### Messaging system methods ###
 # ================================
    def _register_robot_mailbox(self, agent):
        self.agent_mailboxes[agent.agent_id] = Mailbox()
        self.agent_index_by_id[agent.agent_id] = agent

    def get_new_messages(self, recipient_id):
        mailbox = self.agent_mailboxes.get(recipient_id)
        if mailbox is None:
            return []
        return mailbox.pop_new_messages()

    def send_message(self, sender_id, recipient_id, performative, content):
        mailbox = self.agent_mailboxes.get(recipient_id)
        if mailbox is None:
            return
        mailbox.receive_message(
            Message(
                sender_id=sender_id,
                recipient_id=recipient_id,
                performative=performative,
                content=content,
            )
        )

    def broadcast_message(self, sender_id, performative, content, recipient_filter=None):
        sent = 0
        for recipient_id, recipient in self.agent_index_by_id.items():
            if recipient_id == sender_id:
                continue
            if recipient_filter and not recipient_filter(recipient):
                continue
            self.send_message(sender_id, recipient_id, performative, content)
            sent += 1
        return sent

    def broadcast_to_color(self, sender_id, color, performative, content, inventory_state=None):
        def _recipient_filter(agent):
            if getattr(agent, "team_color", None) != color:
                return False
            if inventory_state == "empty":
                return len(agent.inventory) == 0
            if inventory_state == "not_empty_target_waste":
                return len(agent.inventory)  > 0 and agent.inventory[0].waste_type == agent.target_waste_type
            return True

        return self.broadcast_message(
            sender_id=sender_id,
            performative=performative,
            content=content,
            recipient_filter=_recipient_filter,
        )

    def send_agent_message(self, agent):
        pending_batch = list(getattr(agent, "pending_messages", []) or [])
        pending_single = getattr(agent, "pending_message", None)
        if pending_single is not None:
            pending_batch.append(pending_single)

        if not pending_batch:
            return self.get_percepts(agent)

        sent_count = 0
        for pending in pending_batch:
            mode = pending.get("mode")
            performative = pending.get("performative")
            content = pending.get("content", {})

            if mode == "direct":
                recipient_id = pending.get("recipient_id")
                if recipient_id is not None:
                    self.send_message(agent.agent_id, recipient_id, performative, content)
                    sent_count += 1
            elif mode == "broadcast_color":
                color = pending.get("color")
                inventory_state = pending.get("inventory_state")
                if color is not None:
                    sent_count += self.broadcast_to_color(
                        sender_id=agent.agent_id,
                        color=color,
                        performative=performative,
                        content=content,
                        inventory_state=inventory_state,
                    )

        # Store lightweight telemetry for visualization.
        if sent_count > 0:
            agent.last_message_sent_step = self.steps
            agent.last_message_sent_count = sent_count

        if hasattr(agent, "pending_messages") and agent.pending_messages is not None:
            agent.pending_messages.clear()
        agent.pending_message = None
        return self.get_percepts(agent)
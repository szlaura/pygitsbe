from pyboolnet.file_exchange import bnet2primes
from pyboolnet.trap_spaces import compute_trap_spaces
from gitsbe.utils.Util import Util
import mpbn
import random
import pyboolnet


class BooleanModel:
    def __init__(self, model=None,  file='', attractor_tool='', mutation_type='mixed', model_name='', equations = None,
                 fitness=0, binary=None):
        """
        Initializes the BooleanModel instance.
        :param model: An InteractionModel instance.
        :param file: The path to the file containing Boolean Equations in '.bnet' format.
        :param attractor_tool: Tool to be used for attractor calculation.
        (Supported values 'biolqm_trapspaces', 'biolqm_stable_states', 'mpbn_trapspaces', 'pyboolnet_trapspaces')
        :param model_name: Name of the model.
        """
        self._model_name = model_name
        self._boolean_equations = []
        self._updated_boolean_equations = []
        self._attractors = {}
        self._attractor_tool = attractor_tool
        self._fitness = fitness
        self._file = file
        self._equations = equations
        self._binary_boolean_equations = [] if binary is None else binary
        self._is_bnet_file = False
        self._bnet_equations = ''
        self._mutation_type = mutation_type
        self._perturbations =  []
        self._global_output = 0.0

        if model is not None:
            self.init_from_model(model)
        elif self._file:
            self.init_from_bnet_file(file)
        elif self._equations is not None:
            self.init_from_equations(equations)
        else:
            raise ValueError('Please provide a model or a file for the initialization')

        self.to_binary(self._mutation_type)

    def init_from_model(self, model) -> None:
        """
        Initialize the BooleanModel from an InteractionModel instance.
        :param model: The InteractionModel instance containing interactions.
        """
        self._model_name = model.model_name
        interactions = model

        for i in range(interactions.size()):
            equation = self.create_equation_from_interaction(interactions, i)
            self._boolean_equations.append(equation)

        self._updated_boolean_equations = [tuple(item) for item in self._boolean_equations]

    def init_from_bnet_file(self, file: str) -> None:
        """
        Initialize the BooleanModel from a '.bnet' file.
        :param file: The directory of the '.bnet' file.
        """
        print(f"Loading Boolean model from file: {file}")
        try:
            with open(file, 'r') as model_file:
                lines = model_file.readlines()

        except IOError as e:
            raise IOError(f"Error reading file: {e}")

        if Util.get_file_extension(file) != 'bnet':
            raise IOError('ERROR: The extension needs to be .bnet!')

        self._boolean_equations = []
        self._model_name = file.rsplit('.', 1)[0]

        for line in lines:
            if line.strip().startswith('#') or line.strip().startswith('targets') or not line.strip():
                continue
            equation = line.strip()
            parsed_equation_bnet = self._create_equation_from_bnet(equation)
            self._bnet_equations += f"{equation}\n"
            self._boolean_equations.append(parsed_equation_bnet)
            self._is_bnet_file = True

        self._updated_boolean_equations = [tuple(equation) for equation in self._boolean_equations]

    def init_from_equations(self, variable):
        self._boolean_equations = variable
        self._updated_boolean_equations = variable

    def add_perturbations(self, perturbations):
        self._perturbations = perturbations
        for drug in perturbations:
            effect = drug['effect']
            targets = drug['targets']
            self.perturb_nodes(targets, effect)

    def calculate_attractors(self, attractor_tool: str) -> None:
        """
        calculates the attractors of the boolean model. The tool for the calculation
        is based on the value of 'self.attractor_tool'.
        Values for 'self.attractor_tool' (please choose one):
        'mpbn_trapspaces', 'pyboolnet_trapspaces'
        :param attractor_tool:
        """
        if 'mpbn' in attractor_tool:
            self._calculate_attractors_mpbn()
        else:
            self._calculate_attractors_pyboolnet()

    def _calculate_attractors_mpbn(self):
        if self._is_bnet_file:
            result = self._bnet_equations
            self._is_bnet_file = False
        else:
            result = self.to_bnet_format(self._updated_boolean_equations)

        bnet_dict = Util.bnet_string_to_dict(result)
        boolean_network_mpbn = mpbn.MPBooleanNetwork(bnet_dict)
        self._attractors = list(boolean_network_mpbn.attractors())
        print(f"\nMPBN found {len(self._attractors)} attractor(s):\n{self._attractors}")

    def _calculate_attractors_pyboolnet(self):
        if self._is_bnet_file:
            result = self._bnet_equations
            self._is_bnet_file = False
        else:
            result = self.to_bnet_format(self._updated_boolean_equations)

        primes = bnet2primes(result)
        self._attractors = compute_trap_spaces(primes)
        print(f"PyBoolNet found {len(self._attractors)} attractor(s):\n{self._attractors}")

    def get_index_of_equation(self, node_name: str) -> int:
        """
        Gets the index of the equation for a given node name.
        :param node_name: The name of the node.
        :return: The index of the equation or -1 if not found.
        """
        for index, equation in enumerate(self._updated_boolean_equations):
            target, *_ = equation
            if target == node_name:
                return index
        return -1

    def calculate_global_output(self, model_outputs, normalized=True) -> float:
        """
        Use this function after you have calculated attractors with the calculate_attractors function
        in order to find the normalized globaloutput of the model, based on the weights of the nodes
        defined in the ModelOutputs class.
        :return: float
        """
        if not self._attractors:
            raise ValueError("No attractors found. Ensure calculate_attractors() has been called.")

        pred_global_output = 0.0

        for attractor in self._attractors:
            for node_name, node_weight in model_outputs.model_outputs.items():
                if node_name not in attractor:
                    continue
                node_state = attractor[node_name]
                state_value = int(node_state) if node_state in [0, 1] else 0.5
                pred_global_output += state_value * node_weight

        pred_global_output /= len(self._attractors)
        if normalized:
            self._global_output = (pred_global_output - model_outputs.min_output) / (
                    model_outputs.max_output - model_outputs.min_output)
        else:
            self._global_output = pred_global_output
        return self._global_output

    def from_binary(self, binary_representation, mutation_type: str):
        """
        Updates the Boolean Equations from a binary representation based on the mutation type.
        :param binary_representation: The binary representation of the Boolean Equations as a list.
        :param mutation_type: The type of mutation can be: 'topology', 'balanced', 'mixed'
        :return: None
        """
        index = 0
        updated_equations = []
        new_link = ''

        for equation in self._updated_boolean_equations:
            target, activating, inhibitory, act_operators, inhib_operators, link = equation

            if mutation_type == 'topology':
                num_activating = len(activating)
                num_inhibitory = len(inhibitory)

                new_activating_values = binary_representation[index:index + num_activating]
                index += num_activating
                new_inhibitory_values = binary_representation[index:index + num_inhibitory]
                index += num_inhibitory

                new_activating = {key: int(val) for key, val in zip(activating.keys(), new_activating_values)}
                new_inhibitory = {key: int(val) for key, val in zip(inhibitory.keys(), new_inhibitory_values)}

                updated_equations.append((target, new_activating, new_inhibitory, act_operators, inhib_operators, link))

            elif mutation_type == 'balanced':
                if link != '':
                    link_value = binary_representation[index]
                    index += 1

                    new_link = 'and' if link_value == 1 else 'or'
                    updated_equations.append((target, activating, inhibitory, act_operators, inhib_operators, new_link))
                else:
                    updated_equations.append((target, activating, inhibitory, act_operators, inhib_operators, link))

            elif mutation_type == 'mixed':
                num_activating = len(activating)
                num_inhibitory = len(inhibitory)

                new_activating_values = binary_representation[index:index + num_activating]
                index += num_activating
                new_inhibitory_values = binary_representation[index:index + num_inhibitory]
                index += num_inhibitory
                if link != '':
                    link_value = binary_representation[index]
                    index += 1
                    new_link = 'and' if link_value == 1 else 'or'
                    new_activating = {key: val for key, val in zip(activating.keys(), new_activating_values)}
                    new_inhibitory = {key: val for key, val in zip(inhibitory.keys(), new_inhibitory_values)}
                    updated_equations.append((target, new_activating, new_inhibitory,
                                              act_operators, inhib_operators, new_link))
                else:
                    new_activating = {key: val for key, val in zip(activating.keys(), new_activating_values)}
                    new_inhibitory = {key: val for key, val in zip(inhibitory.keys(), new_inhibitory_values)}

                    updated_equations.append((target, new_activating, new_inhibitory,
                                              act_operators, inhib_operators, link))

        self._updated_boolean_equations = updated_equations
        return self._updated_boolean_equations

    def to_binary(self, mutation_type: str):
        """
        Converts the Boolean Equations to a binary representation. It is based on the mutation type.
        :param mutation_type: The type of mutation can be: 'topology', 'balanced', 'mixed'
        :return: The binary representation of the Boolean Equations as a list.
        """
        binary_lists = []

        for equation in self._updated_boolean_equations:
            _, activating, inhibitory, _, _, link = equation

            binary_representation = []

            if mutation_type == 'topology':
                activating_values = [int(value) for value in activating.values()]
                inhibitory_values = [int(value) for value in inhibitory.values()]
                binary_representation.extend(activating_values)
                binary_representation.extend(inhibitory_values)

            elif mutation_type == 'balanced':
                if link != '':
                    binary_representation.append(1 if link == 'and' else 0)
                else:
                    pass

            elif mutation_type == 'mixed':
                activating_values = [int(value) for value in activating.values()]
                inhibitory_values = [int(value) for value in inhibitory.values()]
                binary_representation.extend(activating_values)
                binary_representation.extend(inhibitory_values)
                if link == 'and':
                    binary_representation.append(1)
                elif link == 'or':
                    binary_representation.append(0)
                else:
                    pass

            binary_lists.append(binary_representation)

        equation_lists = [item for sublist in binary_lists for item in sublist]
        self._binary_boolean_equations = equation_lists
        return equation_lists

    def generate_mutated_lists(self, num_mutations, num_mutations_per_list):
        list_length = len(self._binary_boolean_equations)
        mutated_lists = []

        for _ in range(num_mutations):
            mutated_list = self._binary_boolean_equations.copy()
            for _ in range(num_mutations_per_list):
                index_to_mutate = random.randint(0, list_length - 1)
                mutated_list[index_to_mutate] = 1 - mutated_list[index_to_mutate]
            mutated_lists.append(mutated_list)

        return mutated_lists

    def create_equation_from_interaction(self, interaction, interaction_index):
        """
        Create a Boolean equation from an interaction model.
        :param interaction: InteractionModel instance.
        :return: Equation dictionary with components.
        """
        activating_regulators = {}
        inhibitory_regulators = {}
        operators_activating_regulators = []
        operators_inhibitory_regulators = []

        target = interaction.get_target(interaction_index)
        tmp_activating_regulators = interaction.get_activating_regulators(interaction_index)
        tmp_inhibitory_regulators = interaction.get_inhibitory_regulators(interaction_index)
        link = '' if not tmp_activating_regulators or not tmp_inhibitory_regulators else 'and'

        for i, regulator in enumerate(tmp_activating_regulators):
            activating_regulators[regulator] = 1
            if i < (len(tmp_activating_regulators) - 1):
                operators_activating_regulators.append('or')

        for i, regulator in enumerate(tmp_inhibitory_regulators):
            inhibitory_regulators[regulator] = 1
            if i < (len(tmp_inhibitory_regulators) - 1):
                operators_inhibitory_regulators.append('or')

        return(target, activating_regulators, inhibitory_regulators, operators_activating_regulators,
            operators_inhibitory_regulators, link,)


    def create_equation_from_bnet(self, equation_str):
        activating_regulators = {}
        inhibitory_regulators = {}
        operators_activating_regulators = []
        operators_inhibitory_regulators = []
        link = ''

        arg = (equation_str.strip()
               .replace(', ', ' *= ')
               .replace('!', ' not ')
               .replace('&', ' and ')
               .replace('|', ' or '))
        split_arg = arg.split()
        target = split_arg.pop(0)
        if split_arg.pop(0) != '*=':
            raise ValueError("Equation must start with ','")

        before_not = True

        for regulator in split_arg:
            if regulator == 'not':
                before_not = not before_not
            elif regulator in ('and', 'or'):
                if before_not:
                    operators_activating_regulators.append(regulator)
                    link = 'and'
                else:
                    operators_inhibitory_regulators.append(regulator)
                    link = 'or'
            elif regulator in ('(', ')'):
                continue
            else:
                if before_not:
                    activating_regulators[regulator] = 1
                else:
                    inhibitory_regulators[regulator] = 1
                    before_not = True

        link = '' if not activating_regulators or not inhibitory_regulators else 'and'

        interaction_tuple = (
            target,
            activating_regulators,
            inhibitory_regulators,
            operators_activating_regulators,
            operators_inhibitory_regulators,
            link
        )

        return interaction_tuple

    def to_bnet_format(self, boolean_equations):
        equation_list = []

        for eq in boolean_equations:
            target, activating_regulators, inhibitory_regulators, _, _, link = eq

            target_value = f"{target}, "
            link_operator = {'and': '&', 'or': '|'}.get(link, '')

            activation_terms = [regulator for regulator, value in activating_regulators.items() if value == 1]
            inhibition_terms = [f"!{regulator}" for regulator, value in inhibitory_regulators.items() if value == 1]

            activation_expression = " | ".join(activation_terms)
            inhibition_expression = " | ".join(inhibition_terms)

            if activation_expression and inhibition_expression:
                combined_expression = f"{activation_expression} {link_operator} {inhibition_expression}"
            elif activation_expression or inhibition_expression:
                combined_expression = activation_expression or inhibition_expression
            else:
                combined_expression = '0'

            equation_line = f"{target_value.strip()} {combined_expression.strip()}"
            modified_line = equation_line.replace('(', '').replace(')', '')
            equation_list.append(modified_line)

        final_equation_list = '\n'.join(equation_list)
        return final_equation_list

    def print(self):
        equation_list = ''
        for eq in self._updated_boolean_equations:
            equation = ''
            target, activating, inhibitory, _, _, link = eq

            activating_nodes = [node for node, value in activating.items() if value == 1]
            inhibitory_nodes = [node for node, value in inhibitory.items() if value == 1]

            if activating_nodes and inhibitory_nodes:
                activating_part = ' or '.join(activating_nodes)
                inhibitory_part = ' or '.join(inhibitory_nodes)
                equation += f"{target} *= ({activating_part}) {link} not ({inhibitory_part})"
            elif activating_nodes and not inhibitory_nodes:
                activating_part = ' or '.join(activating_nodes)
                equation += f"{target} *= {activating_part}"
            elif inhibitory_nodes and not activating_nodes:
                inhibitory_part = ' or '.join(inhibitory_nodes)
                equation += f"{target} *= not {inhibitory_part}"
            else:
                equation += f"{target} *= 0"

            equation_list += equation
            equation_list += '\n'

        print(equation_list)

    def perturb_nodes(self, node_names, effect):
        value = 0 if effect == 'inhibits' else 1

        for node in node_names:
            for i, equation in enumerate(self._updated_boolean_equations):
                target, _, _, _, _, _ = equation
                if node == target:
                    new_equation = (node, {str(value): 1}, {}, [], [], '')
                    self._updated_boolean_equations[i] = new_equation
                    # print('success, updated:', new_equation)
                    break

    def apply_perturbations(self, perturbations):
        """
        Apply a list of perturbations to the current Boolean model.
        :param perturbations: A list of perturbations where each perturbation is a dictionary with 'targets' and 'effect'.
        """
        for drug in perturbations:
            effect = drug['effect']
            targets = drug['targets']
            self.perturb_nodes(targets, effect)

    def clone(self):
        """
        Create a deep copy of the BooleanModel instance.
        """
        return BooleanModel(
            model_name=self._model_name,
            attractor_tool=self._attractor_tool,
            mutation_type=self._mutation_type,
            fitness=self._fitness,
            equations=self._updated_boolean_equations.copy(),
            binary=self._binary_boolean_equations.copy()
        )

    def _create_equation_from_bnet(self, equation_str):
        activating_regulators = {}
        inhibitory_regulators = {}
        operators_activating_regulators = []
        operators_inhibitory_regulators = []
        link = ''

        arg = (equation_str.strip().replace(', ', ' *= ').replace('!', ' not ')
               .replace('&', ' and ').replace('|', ' or '))
        split_arg = arg.split()
        target = split_arg.pop(0)
        if split_arg.pop(0) != '*=':
            raise ValueError("Equation must start with '*='")

        before_not = True

        for regulator in split_arg:
            if regulator == 'not':
                before_not = not before_not
            elif regulator in ('and', 'or'):
                if before_not:
                    operators_activating_regulators.append(regulator)
                else:
                    operators_inhibitory_regulators.append(regulator)
            elif regulator in ('(', ')'):
                continue
            else:
                if before_not:
                    activating_regulators[regulator] = 1
                else:
                    inhibitory_regulators[regulator] = 1
                    before_not = True

        link = '' if not activating_regulators or not inhibitory_regulators else 'and'

        return (target, activating_regulators, inhibitory_regulators,
                operators_activating_regulators, operators_inhibitory_regulators, link)

    def reset_attractors(self) -> None:
        self._attractors = []

    def has_attractors(self) -> bool:
        return bool(self._attractors)

    def has_stable_states(self) -> bool:
        return bool(self.get_stable_states())

    def has_global_output(self) -> bool:
        return bool(self.global_output)

    def get_stable_states(self) -> object:
        return [state for state in self._attractors if '-' not in state]

    @property
    def mutation_type(self) -> str:
        return self._mutation_type

    @property
    def perturbations(self):
        return self._perturbations

    @property
    def global_output(self):
        return self._global_output

    @property
    def updated_boolean_equations(self):
        return self._updated_boolean_equations

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def fitness(self):
        return self._fitness

    @property
    def attractors(self) -> object:
        return self._attractors

    @property
    def bnet_equations(self):
        return self._bnet_equations

    @property
    def binary_boolean_equations(self):
        return self._binary_boolean_equations

    @property
    def attractor_tool(self) -> str:
        return self._attractor_tool

    @property
    def boolean_equations(self):
        return self._boolean_equations

    @model_name.setter
    def model_name(self, model_name: str) -> None:
        self._model_name = model_name

    @fitness.setter
    def fitness(self, fitness: float) -> None:
        self._fitness = fitness

    @updated_boolean_equations.setter
    def updated_boolean_equations(self, updated_boolean_equations: dict) -> None:
        self._updated_boolean_equations = updated_boolean_equations
from itertools import islice

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from pulser import Pulse, Sequence
from pulser.devices import Chadoq2
from pulser.waveforms import InterpolatedWaveform
from pulser_simulation import QutipEmulator
from scipy.optimize import minimize


## Calculating the cost of a single configuaration of the graph
def get_cost(bitstring, G, penalty=10):  # 10
    z = np.array(list(bitstring), dtype=int)
    A = np.array(nx.adjacency_matrix(G).todense())

    # Add penalty and bias:
    cost = penalty * (z.T @ np.triu(A) @ z) - np.sum(z)
    return cost


## Weighted average over all the configurations of the graph
def get_avg_cost(counts, G, penalty_term):
    avg_cost = sum(counts[key] * get_cost(key, G, penalty_term) for key in counts)
    avg_cost = avg_cost / sum(counts.values())  # Divide by total samples

    return avg_cost


## Cost function to minimize
def func(param, *args):
    # print(args)
    G = args[0][0]
    register = args[0][1]
    C = quantum_loop(param, register)
    cost = get_avg_cost(C, G, args[0][2])

    return cost


def adiabatic_sequence(device, register, time, Omega=3.271543, detuning=5):
    """Creates the adiabatic sequence

    Args:
        device: physical device simulation
        Omega: Frecuency
        register: arrangement of atoms in a quantum processor
        time: time of the adiabatic process
        detuning: detuning use

    Returns:
        sequence
    """

    delta_0 = -detuning
    delta_f = -delta_0

    adiabatic_pulse = Pulse(
        InterpolatedWaveform(time, [1e-9, Omega, 1e-9]),
        InterpolatedWaveform(time, [delta_0, 0, delta_f]),
        0,
    )

    sequence = Sequence(register, device)
    sequence.declare_channel("ising", "rydberg_global")
    sequence.add(adiabatic_pulse, "ising")

    return sequence


# Building the quantum loop


def quantum_loop(parameters, register):
    params = np.array(parameters)

    parameter_time, parameter_omega, parameter_detuning = np.reshape(params.astype(int), 3)
    seq = adiabatic_sequence(
        Chadoq2,
        register,
        parameter_time,
        Omega=parameter_omega,
        detuning=parameter_detuning,
    )

    simul = QutipEmulator.from_sequence(seq, sampling_rate=0.1)
    res = simul.run()
    counts = res.sample_final_state(N_samples=1000)  # Sample from the state vector
    # print(counts)

    return counts


def VQAA(
    atomic_register,
    graph,
    penalty,
    omega_range=(1, 5),
    detuning_range=(1, 5),
    time_range=(8, 25),
    minimizer_method="Nelder-Mead",
    repetitions=10,
):
    scores = []
    params = []
    testing = []
    for repetition in range(repetitions):
        testing.append(repetition)
        random_omega = np.random.uniform(omega_range[0], omega_range[1])
        random_detuning = np.random.uniform(detuning_range[0], detuning_range[1])
        random_time = 1000 * np.random.randint(time_range[0], time_range[1])

        res = minimize(
            func,
            args=[graph, atomic_register, penalty],
            x0=np.r_[random_time, random_omega, random_detuning],
            method=minimizer_method,
            tol=1e-5,
            options={"maxiter": 20},
        )

        # print(res.fun)
        scores.append(res.fun)
        params.append(res.x)

    optimal_parameters = params[np.argmin(scores)]

    return optimal_parameters


def solver_VQAA(
    atomic_register,
    graph,
    penalty_term,
    number_best_solutions=5,
    omega_range=(1, 5),
    detuning_range=(2, 5),
    time_range=(8, 28),
    minimizer_method="Nelder-Mead",
    repetitions=10,
):
    """Variational Quantum Adiabatic Algorithm solver

    Args:
        atomic_register: The atomic register representing the problem in the quantum device
        graph: The networkx graph used before the encoding to the register
        penalty_term: Penalty term for the cost fucntion to optimize
        number_best_solutions: The amount of solutions to output from the best ones
        omega_range: The range of frequencies to used for the optimizer parameters. Default (1,5)
        detuning_range: The range of detuning to used for the optimizer parameters. Default (1,5)
        time_range:Range of time evolution for QAA to used in optimizer parameters.Default (8,25)
        minimizer_method: Minimizer to use from scipy. Default Nelder-Mead
        repetitions: The number of times to repeat the optimization. Default(10)

    Returns:
        counts_sorted: The dictionary of counts of the QAA with the optimal parameters
        opt_params:  Optimal parameters for the QAA
        solution: The list of solutions given the optimal parameters

    """

    opt_params = VQAA(
        atomic_register,
        graph,
        penalty_term,
        omega_range,
        detuning_range,
        time_range,
        minimizer_method,
        repetitions,
    )

    counts = quantum_loop(opt_params, atomic_register)

    counts_sorted = dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    solution = []
    for item in islice(
        counts_sorted,
        number_best_solutions,
    ):  # use islice(d.items(), 3) to iterate over key/value pairs
        element = 0
        solutions_iterations = []
        for bit_solution in item:
            if int(bit_solution) == 1:
                solutions_iterations.append(atomic_register.qubit_ids[element])
            element += 1
        solution.append(solutions_iterations)

    return counts_sorted, opt_params, solution


def plot_distribution(C):
    C = dict(sorted(C.items(), key=lambda item: item[1], reverse=True))
    plt.figure(figsize=(12, 6))
    plt.xlabel("bitstings")
    plt.ylabel("counts")
    plt.bar(C.keys(), C.values(), width=0.5)
    plt.xticks(rotation="vertical")
    plt.show()

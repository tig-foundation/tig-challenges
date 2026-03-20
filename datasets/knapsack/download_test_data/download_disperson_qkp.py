import numpy as np
import os

budget_fractions = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75]

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
TIG_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", ".."))
TEST_ROOT = os.path.join(TIG_ROOT, "datasets", "knapsack", "test")


def write_file(nodes, edges, weights, budget, folder_name, file_name, weight_type='int'):
    """Write one TIG instance file with a single budget on the last line."""

    out_dir = os.path.join(TEST_ROOT, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, file_name)

    n_nodes = len(nodes)
    n_edges = len(edges)
    with open(out_path, 'w') as f:
        f.write('{:d} {:d} {:s}\n'.format(n_nodes, n_edges, weight_type))

        for (i, j) in edges:
            if weight_type == 'int':
                f.write('{:d} {:d} {:d}\n'.format(i, j, edges[(i, j)]))
            else:
                f.write('{:d} {:d} {:.6f}\n'.format(i, j, edges[(i, j)]))

        for weight in weights:
            f.write('{:d} '.format(weight))
        f.write('\n')

        f.write('{:d}\n'.format(budget))


def generate_geometrical_problem_instance(n_nodes):

    # Generate random locations within a 100x100 square for n nodes
    locations = np.random.rand(n_nodes, 2) * 100

    # Calculate the Euclidean distance matrix between the points
    distances = np.sqrt(np.sum((locations[:, np.newaxis] - locations[np.newaxis, :]) ** 2, axis=2))

    return distances


def generate_weighted_geometrical_problem_instance(n_nodes):

    # Generate random locations within a 100x100 square for n nodes
    locations = np.random.rand(n_nodes, 2) * 100

    # Assign random weights to each location within the range [5, 10]
    weights = np.random.uniform(5, 10, size=n_nodes)

    # Calculate the weighted Euclidean distance matrix between the points
    distances = np.outer(weights, weights) * np.sqrt(
        np.sum((locations[:, np.newaxis] - locations[np.newaxis, :]) ** 2, axis=2))

    return distances


def generate_exponential_problem_instance(n_nodes, mean=50):

    # Generate a distance matrix where each entry is drawn from an exponential distribution
    distances = np.random.exponential(mean, size=(n_nodes, n_nodes))

    # Make the distance matrix symmetric since distance from i to j is the same as from j to i
    distances = (distances + distances.T) / 2

    # Set the diagonal to 0 as the distance from a point to itself is 0
    np.fill_diagonal(distances, 0)

    return distances


def generate_random_problem(n_nodes):

    # Generate a distance matrix where each entry is a random integer between 1 and 100
    distances = np.random.randint(1, 101, size=(n_nodes, n_nodes))

    # Make the distance matrix symmetric
    distances = (distances + distances.T) // 2

    # Set the diagonal to 0 as the distance from a point to itself is 0
    np.fill_diagonal(distances, 0)

    return distances


def generate_weights(n_nodes):

    # Generate random weights for each location, each an integer between 1 and 100
    weights = np.random.randint(1, 101, size=n_nodes)

    return weights


# %% Generate instances of Dispersion-QKP collection

# Number of nodes
n_nodes_values = [300, 500, 1000, 2000]
instance_types = ['geo', 'wgeo', 'expo', 'ran']
sparsification_fractions = [0.05, 0.1, 0.25, 0.5, 0.75, 1]

# Generate instances for each value of n_nodes_values
for n_nodes in n_nodes_values:

    # Set random seed
    np.random.seed(24)

    # Generate nodes
    nodes = np.arange(n_nodes)

    # Get weights
    weights = generate_weights(n_nodes)

    for instance_type in instance_types:

        # Sparsify utility matrix
        for sparsification_fraction in sparsification_fractions:

            # Generate edges
            if instance_type == 'geo':
                utility_matrix = generate_geometrical_problem_instance(n_nodes)
            elif instance_type == 'wgeo':
                utility_matrix = generate_weighted_geometrical_problem_instance(n_nodes)
            elif instance_type == 'expo':
                utility_matrix = generate_exponential_problem_instance(n_nodes)
            else:
                utility_matrix = generate_random_problem(n_nodes)

            # Sparsify utility matrix
            utility_matrix = utility_matrix * (np.random.rand(n_nodes, n_nodes) < sparsification_fraction)

            edges = {}
            for i in range(n_nodes):
                for j in range(i + 1, n_nodes):
                    if utility_matrix[i, j] > 0:
                        edges[i, j] = utility_matrix[i, j]

            weight_sum = int(np.sum(weights))
            for budget_fraction in budget_fractions:
                budget = int(budget_fraction * weight_sum)
                fname = 'dispersion-qkp-{:s}_{:d}_{:d}_b{:04d}.txt'.format(
                    instance_type,
                    n_nodes,
                    int(sparsification_fraction * 100),
                    int(budget_fraction * 1000),
                )
                write_file(
                    nodes,
                    edges,
                    weights,
                    budget,
                    'Dispersion-QKP',
                    fname,
                    weight_type='float',
                )
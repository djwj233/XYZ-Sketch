"""Restore the original prime-field experiment's engine arguments from its records."""
import hashlib
import math
from common import ROOT, load


def arguments(job, dataset):
    row = job['expected_paper']
    algorithm = row['algorithm']
    resource = row['resource']
    profile = load(ROOT / 'results/paper/profile_manifest.json')['profiles'][algorithm]

    def seed(role):
        # Same seed domain and role binding as the original Figure-2 protocol.
        material = 'figure2|114514|%s|%d|%d|%s|%s|%s' % (
            row['domain'], row['d'], row['trial_index'], algorithm,
            row['profile_hash'], role)
        return int.from_bytes(hashlib.sha256(material.encode('ascii')).digest()[:8], 'big')

    command = ['--run', str(dataset)]
    if algorithm == 'xyz':
        a = profile['a']
        z = math.floor(profile['gamma'] * (1 - a) ** (2 / 3) * resource ** (1 / 3) + 0.5)
        return command + [str(resource), repr(a), str(z), str(seed('primary'))]
    if algorithm == 'minisketch':
        return command + [str(seed('primary'))]
    if algorithm == 'riblt':
        return command + [str(resource), str(seed('siphash_k0')),
                          str(seed('siphash_k1')), str(seed('primary'))]
    if algorithm in ['external_iblt', 'project_iblt']:
        return command + [str(resource)]
    if algorithm == 'cpisync':
        return command
    raise ValueError('Unknown paper algorithm: ' + algorithm)

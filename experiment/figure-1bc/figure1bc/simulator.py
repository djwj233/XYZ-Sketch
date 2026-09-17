"""Independent ideal-cell hypergraph placement and deterministic peeling."""

import hashlib
import heapq
import math
import struct
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from . import constants as const


WordTriple = Tuple[int, int, int]
Support = Tuple[int, ...]


@dataclass(frozen=True)
class PlacementGeometry:
    M: int
    a: float
    z: int
    range_length: int
    naive_base_range: int
    extra_circular_anchors: int
    circular_base_range: int

    @classmethod
    def create(cls, M: int, a: float, z: int) -> "PlacementGeometry":
        if M <= 0:
            raise ValueError("M must be positive")
        if not math.isfinite(a) or not 0.0 <= a < 1.0:
            raise ValueError("placement requires 0 <= a < 1")
        if not 0 <= z < M:
            raise ValueError("placement requires 0 <= z < M")
        range_length = M // (z + 1)
        if range_length < 1:
            raise ValueError("placement range length must be positive")
        naive_base_range = M - range_length + 1
        extra = math.floor(a * range_length)
        circular = min(M, naive_base_range + extra)
        return cls(M, a, z, range_length, naive_base_range, extra, circular)

    @property
    def discrete_key(self) -> Tuple[int, int]:
        return (self.circular_base_range, self.z)


@dataclass(frozen=True)
class PeelResult:
    success: bool
    initial_edges: int
    residual_edges: int
    peeled_edges: int


@dataclass(frozen=True)
class TrialWords:
    words: Tuple[WordTriple, ...]
    stream_sha256: str


def seed_material(
    base_seed: int,
    domain: str,
    d: int,
    M: int,
    trial_index: int,
    edge_index: int,
    role: str,
) -> bytes:
    if domain not in const.SEED_DOMAINS:
        raise ValueError("unknown Figure 1(b)(c) seed domain: %s" % domain)
    if role not in ("anchor_word", "offset_word_1", "offset_word_2"):
        raise ValueError("unknown uniform role: %s" % role)
    if min(d, M, trial_index, edge_index) < 0:
        raise ValueError("seed indices and dimensions must be nonnegative")
    return (
        "figure1bc|%d|%s|%d|%d|%d|%d|%s"
        % (base_seed, domain, d, M, trial_index, edge_index, role)
    ).encode("ascii")


def placement_word(
    base_seed: int,
    domain: str,
    d: int,
    M: int,
    trial_index: int,
    edge_index: int,
    role: str,
) -> int:
    digest = hashlib.sha256(
        seed_material(base_seed, domain, d, M, trial_index, edge_index, role)
    ).digest()
    return int.from_bytes(digest[:4], "big")


def generate_trial_words(
    base_seed: int,
    domain: str,
    d: int,
    M: int,
    trial_index: int,
) -> TrialWords:
    if d <= 0 or M <= 0 or trial_index < 0:
        raise ValueError("trial requires d>0, M>0, trial_index>=0")
    result: List[WordTriple] = []
    stream = hashlib.sha256()
    for edge_index in range(d):
        triple = (
            placement_word(base_seed, domain, d, M, trial_index, edge_index, "anchor_word"),
            placement_word(base_seed, domain, d, M, trial_index, edge_index, "offset_word_1"),
            placement_word(base_seed, domain, d, M, trial_index, edge_index, "offset_word_2"),
        )
        result.append(triple)
        stream.update(struct.pack(">III", *triple))
    return TrialWords(tuple(result), stream.hexdigest())


def place_edge(words: WordTriple, geometry: PlacementGeometry) -> Support:
    anchor_word, offset_word_1, offset_word_2 = words
    anchor = anchor_word % geometry.circular_base_range
    endpoint_1 = (anchor + offset_word_1 % geometry.range_length) % geometry.M
    endpoint_2 = (anchor + offset_word_2 % geometry.range_length) % geometry.M
    if endpoint_1 == endpoint_2:
        return (endpoint_1,)
    if endpoint_1 < endpoint_2:
        return (endpoint_1, endpoint_2)
    return (endpoint_2, endpoint_1)


def place_edges(words: Sequence[WordTriple], geometry: PlacementGeometry) -> Tuple[Support, ...]:
    return tuple(place_edge(triple, geometry) for triple in words)


def peel_supports(M: int, supports: Sequence[Support], ell: int = const.ELL) -> PeelResult:
    if M <= 0 or ell <= 0:
        raise ValueError("peeling requires M>0 and ell>0")
    adjacency: List[List[int]] = [[] for _ in range(M)]
    degrees = [0] * M
    for edge_id, support in enumerate(supports):
        if len(support) not in (1, 2):
            raise ValueError("each deduplicated support must have size one or two")
        if tuple(sorted(set(support))) != tuple(support):
            raise ValueError("support must be sorted and deduplicated")
        for cell in support:
            if not 0 <= cell < M:
                raise ValueError("support cell outside [0,M)")
            adjacency[cell].append(edge_id)
            degrees[cell] += 1

    active_edges = [True] * len(supports)
    queue = [cell for cell, degree in enumerate(degrees) if 1 <= degree <= ell]
    heapq.heapify(queue)
    residual = len(supports)

    while queue:
        cell = heapq.heappop(queue)
        if not 1 <= degrees[cell] <= ell:
            continue
        incident = [edge_id for edge_id in adjacency[cell] if active_edges[edge_id]]
        for edge_id in incident:
            if not active_edges[edge_id]:
                continue
            active_edges[edge_id] = False
            residual -= 1
            for endpoint in supports[edge_id]:
                previous_degree = degrees[endpoint]
                degrees[endpoint] -= 1
                if previous_degree > ell and 1 <= degrees[endpoint] <= ell:
                    heapq.heappush(queue, endpoint)

    return PeelResult(
        success=(residual == 0),
        initial_edges=len(supports),
        residual_edges=residual,
        peeled_edges=len(supports) - residual,
    )


def simulate_words(words: Sequence[WordTriple], geometry: PlacementGeometry) -> PeelResult:
    return peel_supports(geometry.M, place_edges(words, geometry), const.ELL)

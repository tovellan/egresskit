"""Strict JSON and YAML document parsing for security-sensitive inputs."""

from __future__ import annotations

import json
from collections.abc import Hashable
from typing import Any, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, SequenceNode
from yaml.resolver import BaseResolver


class DocumentParseError(ValueError):
    """A document used syntax that the strict loaders reject."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_document(self, node: Node) -> Any:
        _validate_unique_mapping_graph(self, node)
        return super().construct_document(node)


_YAML_MERGE_KEY = object()


def _syntactic_key(
    loader: _UniqueKeySafeLoader,
    node: Any,
    *,
    deep: bool,
) -> Hashable:
    if node.tag == "tag:yaml.org,2002:merge":
        return _YAML_MERGE_KEY
    key = loader.construct_object(node, deep=deep)
    if not isinstance(key, Hashable):
        raise ConstructorError(
            "while constructing a mapping",
            node.start_mark,
            "found an unhashable key",
            node.start_mark,
        )
    return key


def _ensure_unique_syntactic_keys(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
) -> None:
    syntactic_keys: set[Hashable] = set()
    for key_node, _ in node.value:
        key = _syntactic_key(loader, key_node, deep=False)
        if key in syntactic_keys:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
                key_node.start_mark,
            )
        syntactic_keys.add(key)


def _validate_unique_mapping_graph(
    loader: _UniqueKeySafeLoader,
    root: Node,
) -> None:
    pending = [root]
    visited: set[int] = set()
    mappings: list[MappingNode] = []

    while pending:
        node = pending.pop()
        node_identity = id(node)
        if node_identity in visited:
            continue
        visited.add(node_identity)

        if isinstance(node, MappingNode):
            mappings.append(node)
            for key_node, value_node in node.value:
                pending.extend((key_node, value_node))
        elif isinstance(node, SequenceNode):
            pending.extend(node.value)

    for node in mappings:
        _ensure_unique_syntactic_keys(loader, node)


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            )
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentParseError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    del value
    raise DocumentParseError("JSON document contains a nonstandard numeric constant")


def parse_document(raw: str, *, is_json: bool) -> Any:
    """Parse a document while rejecting duplicate mapping keys at every level."""

    if is_json:
        try:
            return json.loads(
                raw,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except DocumentParseError:
            raise
        except ValueError as exc:
            raise DocumentParseError("JSON document is invalid") from exc

    loader = _UniqueKeySafeLoader(raw)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()

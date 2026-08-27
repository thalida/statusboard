from common.ordering import MappedOrderingFilter


def _view(ordering_fields, ordering_map):
    return type(
        "V", (), {"ordering_fields": ordering_fields, "ordering_map": ordering_map}
    )()


def test_a_related_path_ordering_does_not_reach_the_paginator():
    # CursorPagination asserts '__' not in ordering. The map keeps it flat.
    view = _view(["name"], {"status__severity": ["severity_now"]})
    out = MappedOrderingFilter().remove_invalid_fields(
        None, ["-status__severity"], view, None
    )
    assert out == ["-severity_now"]
    assert all("__" not in term for term in out)


def test_an_unmapped_unknown_value_is_dropped():
    view = _view(["name"], {})
    assert (
        MappedOrderingFilter().remove_invalid_fields(None, ["nonsense"], view, None)
        == []
    )


def test_a_value_that_is_not_a_field_expands_to_several():
    # `suggested` is not a column. It is an editorial order.
    view = _view(["name"], {"suggested": ["-is_featured", "-watcher_count"]})
    out = MappedOrderingFilter().remove_invalid_fields(None, ["suggested"], view, None)
    assert out == ["-is_featured", "-watcher_count"]


def test_a_plain_declared_field_passes_through():
    view = _view(["name"], {})
    assert MappedOrderingFilter().remove_invalid_fields(
        None, ["-name"], view, None
    ) == ["-name"]

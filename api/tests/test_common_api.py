import pytest
from rest_framework import serializers

from common.mixins import FieldsMixin
from common.pagination import EnvelopePagination


class Inner(FieldsMixin, serializers.Serializer):
    severity = serializers.IntegerField()
    source = serializers.CharField()


class Outer(FieldsMixin, serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    status = Inner()


DATA = {"id": "1", "name": "Twilio", "status": {"severity": 0, "source": "provider"}}


def _serialize(fields):
    request = type("R", (), {"query_params": {"fields": fields} if fields else {}})()
    return Outer(DATA, context={"request": request}).data


def test_without_the_parameter_every_field_is_returned():
    assert set(_serialize(None)) == {"id", "name", "status"}


def test_the_parameter_selects_top_level_fields():
    assert set(_serialize("id,name")) == {"id", "name"}


def test_a_dotted_path_prunes_inside_a_nested_object_rather_than_dropping_it():
    result = _serialize("id,status.severity")
    assert set(result) == {"id", "status"}
    assert set(result["status"]) == {"severity"}


def test_an_unknown_field_is_ignored_rather_than_erroring():
    # A client asking for a field that does not exist yet gets what does exist.
    assert set(_serialize("id,nonsense")) == {"id"}


def test_a_serializer_can_opt_out():
    class Fixed(FieldsMixin, serializers.Serializer):
        fields_param = None
        a = serializers.CharField()
        b = serializers.CharField()

    request = type("R", (), {"query_params": {"fields": "a"}})()
    assert set(Fixed({"a": "1", "b": "2"}, context={"request": request}).data) == {
        "a",
        "b",
    }


@pytest.mark.django_db
def test_a_non_unique_ordering_gets_the_tiebreak_appended():
    # A cursor needs a unique key. Non-unique ordering repeats or skips rows.
    view = type("V", (), {"ordering": "severity", "filter_backends": []})()
    paginator = EnvelopePagination()
    ordering = paginator.get_ordering(None, None, view)
    assert ordering[-1] == "-created_at"

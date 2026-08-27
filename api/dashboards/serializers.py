from rest_framework import serializers


class TrackComponentSerializer(serializers.Serializer):
    """The body of POST /dashboards/{uuid}/components/.

    The view is a ListCreateAPIView, so without this the schema advertises
    a whole Component as the request. It takes one id.
    """

    component_id = serializers.UUIDField()

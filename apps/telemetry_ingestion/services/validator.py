from rest_framework import serializers


class LightstreamerReadingSerializer(serializers.Serializer):
    item_id = serializers.CharField(required=True)
    timestamp = serializers.DateTimeField(required=True)
    value = serializers.CharField(required=True)
    status = serializers.DictField(required=False)

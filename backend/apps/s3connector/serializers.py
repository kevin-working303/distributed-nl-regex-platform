from rest_framework import serializers


class CredentialsSerializer(serializers.Serializer):
    """Validates inbound AWS credentials. `write_only` everywhere so DRF will
    never echo these values back in a response representation."""

    access_key = serializers.CharField(write_only=True, trim_whitespace=True)
    secret_key = serializers.CharField(write_only=True, trim_whitespace=True)
    bucket = serializers.CharField(trim_whitespace=True)
    region = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_region(self, value):
        return value or None


class ListFilesSerializer(CredentialsSerializer):
    prefix = serializers.CharField(required=False, allow_blank=True, default="")


class ColumnsSerializer(CredentialsSerializer):
    key = serializers.CharField(trim_whitespace=True)

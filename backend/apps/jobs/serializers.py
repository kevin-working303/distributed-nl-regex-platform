from rest_framework import serializers

from apps.s3connector.serializers import CredentialsSerializer

from .models import Job, Operation


class JobCreateSerializer(CredentialsSerializer):
    """Inbound job submission. Inherits write-only AWS credential fields so they
    are validated but never echoed back."""

    file_key = serializers.CharField(trim_whitespace=True)
    operation = serializers.ChoiceField(
        choices=[o.value for o in Operation], default=Operation.REPLACE.value
    )
    description = serializers.CharField(trim_whitespace=True)
    replacement = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=False
    )
    target_columns = serializers.ListField(
        child=serializers.CharField(trim_whitespace=True), allow_empty=False
    )

    def validate(self, attrs):
        if attrs["operation"] == Operation.REPLACE.value and attrs.get("replacement") == "":
            # Empty replacement is valid (deletes matches) but warn-free; allowed.
            pass
        return attrs


class JobSerializer(serializers.ModelSerializer):
    """Outbound job representation. Deliberately excludes encrypted_credentials."""

    class Meta:
        model = Job
        fields = [
            "id",
            "bucket",
            "file_key",
            "operation",
            "description",
            "replacement",
            "target_columns",
            "status",
            "progress",
            "stage",
            "spec",
            "row_count",
            "match_count",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

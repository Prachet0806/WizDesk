from collections.abc import Mapping
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError


class ObjectAPIView(APIView):
    """Reject malformed JSON bodies before handlers access object fields."""
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method in ('POST', 'PUT', 'PATCH') and not isinstance(request.data, Mapping):
            raise ValidationError('The request body must be a JSON object.')

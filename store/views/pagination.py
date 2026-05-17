from rest_framework.exceptions import ValidationError


def get_pagination_params(request) -> tuple[int, int]:
    try:
        skip = int(request.query_params.get("skip", 0))
        limit = int(request.query_params.get("limit", 100))
    except (TypeError, ValueError) as exc:
        raise ValidationError("skip and limit must be integers") from exc

    if skip < 0:
        raise ValidationError("skip must be greater than or equal to 0")
    if limit < 1 or limit > 500:
        raise ValidationError("limit must be between 1 and 500")
    return skip, limit

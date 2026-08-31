from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination for large dataset listings.
    Defaults to 50 items per page with client override up to 500.
    Paginates when 'page' or 'page_size' query parameter is specified.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500

    def paginate_queryset(self, queryset, request, view=None):
        if 'page' in request.query_params or 'page_size' in request.query_params:
            return super().paginate_queryset(queryset, request, view=view)
        return None

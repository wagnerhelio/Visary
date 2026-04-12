class VisaryRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.visary_client_id = request.session.get("client_id")
        request.visary_partner_id = request.session.get("partner_id")
        request.visary_is_client_area = bool(request.visary_client_id)
        request.visary_is_partner_area = bool(request.visary_partner_id)
        return self.get_response(request)

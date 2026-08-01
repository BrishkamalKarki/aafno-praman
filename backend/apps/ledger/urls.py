from django.urls import path

from .views import LedgerStatusView

app_name = "ledger"

urlpatterns = [
    path("status/", LedgerStatusView.as_view(), name="status"),
]

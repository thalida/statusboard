from django.db import models


class StatusPageProvider(models.TextChoices):
    STATUSPAGE = "statuspage", "Atlassian Statuspage"
    INSTATUS = "instatus", "Instatus"
    BETTERSTACK = "betterstack", "Better Stack"
    INCIDENT_IO = "incident_io", "incident.io"
    STATUS_IO = "status_io", "status.io"
    GOOGLE_CLOUD = "google_cloud", "Google Cloud"
    AWS = "aws", "Amazon Web Services"
    RSS = "rss", "RSS feed"

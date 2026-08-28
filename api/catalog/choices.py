from django.db import models


class StatusPageProvider(models.TextChoices):
    STATUSPAGE = "statuspage", "Atlassian Statuspage"
    INSTATUS = "instatus", "Instatus"
    BETTERSTACK = "betterstack", "Better Stack"
    INCIDENT_IO = "incident_io", "incident.io"
    STATUS_IO = "status_io", "status.io"
    CSTATE = "cstate", "cState"
    SALESFORCE = "salesforce", "Salesforce Trust"
    AUTH0 = "auth0", "Auth0"
    GOOGLE_CLOUD = "google_cloud", "Google Cloud"
    AWS = "aws", "Amazon Web Services"
    AZURE = "azure", "Microsoft Azure"
    APPLE = "apple", "Apple"
    ORACLE = "oracle", "Oracle Cloud"
    GOOGLE_FEED = "google_feed", "Google status feed"
    RSS = "rss", "RSS feed"

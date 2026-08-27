from django.db import models


class StatusPageProvider(models.TextChoices):
    STATUSPAGE = "statuspage", "Atlassian Statuspage"
    INSTATUS = "instatus", "Instatus"
    BETTERSTACK = "betterstack", "Better Stack"
    RSS = "rss", "RSS feed"

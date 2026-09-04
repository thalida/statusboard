from django.db import models


class StatusPageProvider(models.TextChoices):
    """The product whose page is read.

    A label goes in a column. Each is the name the product is known by,
    not its full one.
    """

    STATUSPAGE = "statuspage", "Statuspage"
    INSTATUS = "instatus", "Instatus"
    BETTERSTACK = "betterstack", "Better Stack"
    INCIDENT_IO = "incident_io", "incident.io"
    STATUS_IO = "status_io", "status.io"
    CSTATE = "cstate", "cState"
    SALESFORCE = "salesforce", "Salesforce"
    AUTH0 = "auth0", "Auth0"
    GOOGLE_CLOUD = "google_cloud", "Google Cloud"
    AWS = "aws", "AWS"
    AZURE = "azure", "Azure"
    APPLE = "apple", "Apple"
    ORACLE = "oracle", "Oracle"
    GOOGLE_FEED = "google_feed", "Google feed"
    RSS = "rss", "RSS"


class ServiceSource(models.TextChoices):
    """How a service reached the catalog.

    Two values, because there are two writers. `import_from_url` makes
    one, and the admin's add form makes the other. Anything else, such
    as a shell or a migration, reads manual. It was not imported.
    """

    MANUAL = "manual", "Added by hand"
    IMPORT = "import", "Imported from a status page"

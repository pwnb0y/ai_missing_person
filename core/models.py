from django.db import models

class MissingPerson(models.Model):
    id = models.AutoField(primary_key=True)

    # Person Details
    name = models.CharField(max_length=100, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    height = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=50, null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact = models.CharField(max_length=20)  # Required
    last_seen_location = models.CharField(max_length=255)  # Required
    bounty = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image_path = models.CharField(max_length=255)  # Required

    # Reporter Info
    reporter_name = models.CharField(max_length=100)  # Required
    reporter_address = models.TextField(null=True, blank=True)
    reporter_contact = models.CharField(max_length=20, null=True, blank=True)
    message = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name or "Unnamed Person"

from django.db import models


class User(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.CharField(max_length=255, unique=True, db_index=True)
    username = models.CharField(max_length=100, unique=True, db_index=True)
    hashed_password = models.CharField(max_length=255)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)

    class Meta:
        managed = False
        db_table = "users"

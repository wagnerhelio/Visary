import logging

from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from system.models import (
    FinancialRecord,
    FinancialStatus,
    ProcessStatus,
    Trip,
    TripClient,
    TripProcessStatus,
)

logger = logging.getLogger("visary.financial")


def _create_financial_records_for_trip(trip):
    if trip.advisory_fee <= 0:
        return

    with transaction.atomic():
        existing = FinancialRecord.objects.filter(trip=trip)
        clients_with_record = set(
            existing.exclude(client=None).values_list("client_id", flat=True)
        )
        trip_clients = TripClient.objects.filter(trip=trip).select_related("client")

        if trip_clients.exists():
            existing.filter(client=None).delete()
            primary_tc = trip_clients.filter(role="primary").first()
            target = primary_tc or trip_clients.first()
            if target and target.client_id not in clients_with_record:
                FinancialRecord.objects.create(
                    trip=trip,
                    client=target.client,
                    assigned_advisor=trip.assigned_advisor,
                    amount=trip.advisory_fee,
                    status=FinancialStatus.PENDING,
                    created_by=trip.created_by,
                )
                logger.info(
                    "Registro financeiro criado para '%s' (pk=%s), viagem pk=%s",
                    target.client.full_name, target.client_id, trip.pk,
                )
            return

        if not existing.filter(client=None).exists():
            FinancialRecord.objects.create(
                trip=trip,
                client=None,
                assigned_advisor=trip.assigned_advisor,
                amount=trip.advisory_fee,
                status=FinancialStatus.PENDING,
                created_by=trip.created_by,
            )
            logger.info("Registro financeiro sem cliente criado para viagem pk=%s", trip.pk)


def _sync_trip_statuses(trip):
    filter_q = models.Q(visa_type__isnull=True)
    if trip.visa_type_id:
        filter_q |= models.Q(visa_type=trip.visa_type)

    target_ids = set(
        ProcessStatus.objects.filter(filter_q, is_active=True).values_list("id", flat=True)
    )
    current_ids = set(
        TripProcessStatus.objects.filter(trip=trip).values_list("status_id", flat=True)
    )

    to_add = target_ids - current_ids
    to_remove = current_ids - target_ids

    for status_id in to_add:
        TripProcessStatus.objects.create(trip=trip, status_id=status_id)
    if to_remove:
        TripProcessStatus.objects.filter(trip=trip, status_id__in=to_remove).delete()


@receiver(post_save, sender=Trip)
def create_financial_record(sender, instance, created, **kwargs):
    if created and instance.clients.exists():
        _create_financial_records_for_trip(instance)


@receiver(m2m_changed, sender=Trip.clients.through)
def create_financial_record_on_client_add(sender, instance, action, **kwargs):
    if action == "post_add" and instance.pk:
        _create_financial_records_for_trip(instance)


@receiver(post_save, sender=TripClient)
def auto_promote_first_primary(sender, instance, created, **kwargs):
    if not created:
        return
    trip = instance.trip
    if not TripClient.objects.filter(trip=trip, role="primary").exists():
        instance.role = "primary"
        instance.trip_primary_client = None
        instance.save(update_fields=["role", "trip_primary_client", "updated_at"])


@receiver(post_delete, sender=TripClient)
def auto_promote_on_primary_removal(sender, instance, **kwargs):
    if instance.role != "primary":
        return
    next_tc = TripClient.objects.filter(trip_id=instance.trip_id, role="dependent").first()
    if next_tc:
        next_tc.role = "primary"
        next_tc.trip_primary_client = None
        next_tc.save(update_fields=["role", "trip_primary_client", "updated_at"])


@receiver(post_save, sender=Trip)
def sync_trip_statuses_post_save(sender, instance, **kwargs):
    _sync_trip_statuses(instance)


@receiver(post_save, sender=ProcessStatus)
def sync_trip_statuses_on_status_change(sender, instance, **kwargs):
    trips = Trip.objects.all()
    if instance.visa_type_id:
        trips = trips.filter(visa_type=instance.visa_type)
    for trip in trips:
        _sync_trip_statuses(trip)

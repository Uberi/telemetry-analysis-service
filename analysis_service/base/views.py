import logging
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseRedirect

from session_csrf import anonymous_csrf

import kronos

from analysis_service.base import forms
from analysis_service.base import models
from analysis_service.base.util import email


logger = logging.getLogger("django")


@login_required
def dashboard(request):
    username = request.user.email.split("@")[0]
    return render(request, 'analysis_service/dashboard.jinja', context={
        "active_clusters": models.Cluster.objects.filter(created_by=request.user)
                                                 .order_by("start_date"),
        "new_cluster_form": forms.NewClusterForm(initial={
            "identifier": "{}-telemetry-analysis".format(username),
            "size": 1,
        }),
        "active_workers": models.Worker.objects.filter(created_by=request.user)
                                               .order_by("start_date"),
        "new_worker_form": forms.NewWorkerForm(initial={
            "identifier": "{}-telemetry-worker".format(username),
        }),
        "active_scheduled_spark": models.ScheduledSpark.objects.filter(created_by=request.user)
                                                               .order_by("start_date"),
        "new_scheduled_spark_form": forms.NewScheduledSparkForm(initial={
            "identifier": "{}-telemetry-scheduled-task".format(username),
            "size": 1,
            "start_date": datetime.now(),
            "interval_in_hours": 24 * 7,
        }),
    })


@anonymous_csrf
def login(request):
    if request.user.is_authenticated():
        return redirect(dashboard)
    return render(request, 'analysis_service/login.jinja')


@login_required
@anonymous_csrf
@require_POST
def new_cluster(request):
    form = forms.NewClusterForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_json(escape_html=True))

    form.save(request.user)  # this will also magically spawn the cluster for us
    return HttpResponseRedirect("/")


@login_required
@anonymous_csrf
@require_POST
def new_worker(request):
    form = forms.NewWorkerForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_json(escape_html=True))

    form.save(request.user)  # this will also magically create the worker for us
    return HttpResponseRedirect("/")


# this function is called every hour
@kronos.register('0 * * * *')
def clean_up_stragglers():
    now = datetime.now()
    for cluster in models.Cluster.objects.all():
        if cluster.end_date >= now:  # the cluster is expired
            cluster.delete()
        elif cluster.end_date >= now + timedelta(hours=1):  # the cluster will expire in an hour
            email.send_email(
                email_address = cluster.created_by.email,
                subject = "Cluster {} is expiring soon!".format(cluster.identifier),
                body = (
                    "Your cluster {} will be terminated in roughly one hour, as of {}. "
                    "Please save all unsaved work before the machine is shut down.\n"
                    "\n"
                    "This is an automated message from the Telemetry Analysis service. "
                    "See https://analysis.telemetry.mozilla.org/ for more details."
                ).format(cluster.identifier, now)
            )

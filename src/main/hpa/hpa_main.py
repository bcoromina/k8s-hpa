#!/usr/bin/env python3
import os

from kubernetes.client import CoreV1Api, AppsV1Api, CustomObjectsApi

from main.api_groups import deployment_api, custom_objects_api, pod_api, utils

# https://setuptools.pypa.io/en/latest/setuptools.html#develop-deploy-the-project-source-in-development-mode
# https://www.jetbrains.com/pycharm/guide/tutorials/visual_pytest/setup/
os.environ['KUBERNETES_SERVICE_HOST'] = 'kubernetes.default.svc'
os.environ['KUBERNETES_SERVICE_PORT'] = '443'
from kubernetes import client, config

import time
import sys
import requests
import json


def get_namespace():
    if "local" in sys.argv:
        return "my_namespace"
    else:
        return utils.get_incluster_namespace()


# Configs can be set in Configuration class directly or using helper utility #config.load_kube_config(context="k3d-klocal")

def load_config():
    if "local" in sys.argv:
        config.load_kube_config()
    else:
        config.load_incluster_config()


def log_line(str):
    sys.stdout.write(str + '\n')
    sys.stdout.flush()


class CustomAppInfo:

    def get_pod_num_datasets(self, pod_ip):
        num_ds = None
        try:
            url = f"http://{pod_ip}:20610/admin/datasets-info"
            log_line(f"GET {url}")
            ds_infostr = requests.get(url).text
            log_line(f"RESP: {ds_infostr}")
            ds_info = json.loads(ds_infostr)

            num_ds = ds_info['numDataSets']
            lt_str = ds_info['lastTimeAccess']

        except Exception as e:
            log_line(str(e))
            sys.stderr.write(str(e))
        return num_ds


last_scaleup = time.time()


class HpaConfig:

    def __init__(self):
        self.mir = int(os.getenv('MIN_REPLICAS'))
        self.mar = int(os.getenv('MAX_REPLICAS'))
        self.uct = float(os.getenv('UPPER_CPU_THRESHOLD'))  # 0.7
        self.lct = float(os.getenv('LOWER_CPU_THRESHOLD'))  # 0.4
        self.lts = int(os.getenv('LOOP_TIME_S'))  # Amout of time that takes to a pod to be ready
        self.nsdp = int(os.getenv('NO_SCALE_DOWN_PERIOD'))

    @property
    def no_scale_down_period_s(self):
        return self.nsdp

    @property
    def loop_time_s(self) -> float:
        return self.lts

    @property
    def lower_cpu_threshold(self) -> float:
        return self.lct

    @property
    def upper_cpu_threshold(self) -> float:
        return self.uct

    @property
    def min_replicas(self) -> int:
        return self.mir

    @property
    def max_replicas(self) -> int:
        return self.mar


class ClusterActions:
    def __init__(self, core_api_c: CoreV1Api, custom_objects_api_c: CustomObjectsApi, apps_api_c: AppsV1Api, namespace):
        self.core_api_client = core_api_c
        self.custom_objects_api_client = custom_objects_api_c
        self.apps_api_client = apps_api_c
        self.app = "my_app"
        self.role = "web"
        self.service_name = "web"
        self.main_container_name = "web"
        self.hpa_web = "web"
        self.deployment_web = "web"
        self.namespace = namespace

    def get_requested_deployment_cpu(self):
        resource_request = deployment_api.get_deployment_resource_requests(self.apps_api_client, self.deployment_web,
                                                                           self.namespace,
                                                                           self.main_container_name)
        req_cpu_s = resource_request.get("cpu", "0m")

        req_cpu_m = 0
        if 'm' in req_cpu_s:
            req_cpu_m = int(req_cpu_s[:len(req_cpu_s) - 1])

        return req_cpu_m

    def set_deployment_replicas(self, target_replicas):
        deployment_api.set_deployment_replicas(self.apps_api_client, self.deployment_web, self.namespace,
                                               target_replicas)

    def get_deployment_replicas(self):
        return deployment_api.get_deployment_replicas(self.apps_api_client, self.deployment_web, self.namespace)

    def get_name_ip_pairs(self) -> list[tuple[str, str]]:
        return pod_api.get_pods_names_and_ips(
            pod_api.get_ready_pods(self.core_api_client, self.app, self.role, self.namespace, self.main_container_name)
        )

    def get_total_cpu_usage(self, name_ip_pairs: list[tuple[str, str]]) -> float:
        total_cpu_n = 0
        for t in name_ip_pairs:
            name = t[0]
            ip = t[1]
            # logLine(f"Active pod -> Name: {name}, ip: {ip}")
            cpu_n = self.get_pod_cpu_usage(name)
            total_cpu_n += cpu_n
            log_line(f"CPU for pod {name} ({ip}): {cpu_n / 1000000}ms")

        total_cpu_m = total_cpu_n / 1000000
        return total_cpu_m

    def get_pod_cpu_usage(self, name: str) -> int:
        usages = custom_objects_api.get_usages_from_pod(self.custom_objects_api_client, name, self.namespace)
        cpu_n = 0
        if 'n' in usages["cpu"]:
            v = usages["cpu"]
            cpu_n = int(v[:len(v) - 1])
        return cpu_n

    def annotate_pod_deletion_cost(self, name: str, cost: int) -> None:
        self.core_api_client.patch_namespaced_pod(name, self.namespace, body={
            "metadata": {"annotations": {"controller.kubernetes.io/pod-deletion-cost": f"{cost}"}}})

    def delete_pod(self, name):
        self.annotate_pod_deletion_cost(name, 0)
        # coreApiClient.delete_namespaced_pod(name, namespace)
        # scale deployment decrementar el numero de replicar
        current_replicas = self.get_deployment_replicas()
        target_replicas = current_replicas - 1
        # hpaClient.patch_namespaced_horizontal_pod_autoscaler(hpa_web, namespace, body = { "status":{"desiredReplicas": f"{str(target_replicas)}"}})
        self.set_deployment_replicas(target_replicas)
        log_line(f"Replicas set to {target_replicas}")


def scale_down_period(hpa_config, last_scale_up):
    return (time.time() - last_scale_up) > hpa_config.no_scale_down_period_s


from enum import Enum


class ScalerAction(Enum):
    SCALE_UP = 1
    NOTHING = 2
    SCALE_DOWN = 3


def scale_replicas(cluster_actions: ClusterActions,
                   hpa_config: HpaConfig,
                   custom_app_info: CustomAppInfo,
                   last_scale_up: float) -> ScalerAction:
    action = ScalerAction.NOTHING
    log_line(f"Min. replicas: {hpa_config.min_replicas}")
    log_line(f"Max. replicas: {hpa_config.max_replicas}")
    name_ip_pairs: list[tuple[str, str]] = cluster_actions.get_name_ip_pairs()
    num_replicas_ready = len(name_ip_pairs)

    total_cpu_m = cluster_actions.get_total_cpu_usage(name_ip_pairs)
    log_line(f"CPU total: {total_cpu_m} milliCores")
    log_line(f"Deployment replicas: {cluster_actions.get_deployment_replicas()}")

    req_cpu_m = cluster_actions.get_requested_deployment_cpu()

    log_line(f"Req. CPU millis: {req_cpu_m}")

    total_req = req_cpu_m * num_replicas_ready

    upper_cpu_limit = total_req * hpa_config.upper_cpu_threshold
    lower_cpu_limit = total_req * hpa_config.lower_cpu_threshold

    if total_cpu_m > upper_cpu_limit:
        log_line(f"Scale up")
        current_replicas = cluster_actions.get_deployment_replicas()
        if current_replicas < hpa_config.max_replicas and current_replicas == num_replicas_ready:  # no hemos llegado al maximo ni hay pods levantandose
            target_replicas = current_replicas + 1
            cluster_actions.set_deployment_replicas(target_replicas)
            action = ScalerAction.SCALE_UP
    elif lower_cpu_limit < total_cpu_m < upper_cpu_limit:
        log_line(f"Do nothing")
        action = ScalerAction.NOTHING
    else:
        current_replicas = cluster_actions.get_deployment_replicas()
        max_to_kill = num_replicas_ready - hpa_config.min_replicas

        if max_to_kill > 0 and current_replicas == num_replicas_ready and scale_down_period(hpa_config,
                                                                                            last_scale_up):  # si estamos por encima de las replicas mínimas y no hay pods levantándose
            log_line("Scale down")
            num_killed = 0
            for t in name_ip_pairs:
                name = t[0]
                ip = t[1]

                if num_killed < max_to_kill:
                    num_ds = custom_app_info.get_pod_num_datasets(ip)
                    log_line(f"pod {name} ({ip}) has {num_ds} datasets")
                    if num_ds == 0:
                        log_line(f"Pod {name} will be killed for having no datasets")

                        cluster_actions.annotate_pod_deletion_cost(name, 0)
                        current_replicas = cluster_actions.get_deployment_replicas()
                        target_replicas = current_replicas - 1
                        cluster_actions.set_deployment_replicas(target_replicas)
                        log_line(f"Replicas set to {target_replicas}")

                        action = ScalerAction.SCALE_DOWN
                        num_killed += 1
        else:
            log_line(f"Do nothing")

    log_line("------------------------------------------------")
    return action


def main():
    load_config()
    # hpaClient: AutoscalingV1Api = client.AutoscalingV1Api(client.ApiClient())
    cluster_actions = ClusterActions(client.CoreV1Api(),
                                     client.CustomObjectsApi(),
                                     client.AppsV1Api(client.ApiClient()),
                                     get_namespace()
                                     )
    hpa_config = HpaConfig()
    custom_app_info = CustomAppInfo()
    last_scaleup = 0  # enables an initial scaleup
    while True:
        try:
            action = scale_replicas(cluster_actions, hpa_config, custom_app_info, last_scaleup)
            if action == ScalerAction.SCALE_UP:
                last_scaleup = time.time()

        except Exception as e:
            log_line(str(e))
            sys.stderr.write(str(e))
        time.sleep(hpa_config.loop_time_s)


if __name__ == "__main__":
    main()

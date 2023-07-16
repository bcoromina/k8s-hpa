import sys

from kubernetes.client import AutoscalingV1Api


def get_hpa_by_name(hpa_client: AutoscalingV1Api, hpa_name, namespace):
    hpas = hpa_client.list_namespaced_horizontal_pod_autoscaler(namespace)
    return list(filter(lambda hpa: hpa.metadata.name == hpa_name, hpas.items))


def get_min_replicas(hpa_client: AutoscalingV1Api, hpa_name, namespace) -> int:
    min_replicas = 1
    try:
        min_replicas = get_hpa_by_name(hpa_client, hpa_name, namespace)[0].spec.min_replicas
    except Exception as e:
        log_line(str(e))
        sys.stderr.write(str(e))
    return min_replicas


def log_line(message):
    sys.stdout.write(message + '\n')
    sys.stdout.flush()

import logging

from kubernetes.client import CoreV1Api
import threading
from kubernetes import watch


def get_pods_by_namespace(client: CoreV1Api, namespace):
    ret = client.list_pod_for_all_namespaces(watch=False)
    return list(filter(lambda pod: pod.metadata.namespace == namespace, ret.items))


def check_pod_label(pod, label_name, label_value):
    pod_labels = pod.metadata.labels
    result = False
    if label_name in pod_labels.keys():
        result = pod_labels[label_name] == label_value
    return result


def filter_pods_by_label(pods, label_name, label_value):
    return list(filter(lambda pod: check_pod_label(pod, label_name, label_value), pods))


def get_pod_ip(pod):
    return pod.status.pod_ip


def get_pods_ips(pods):
    return list(map(lambda pod: get_pod_ip(pod), pods))


def get_pod_name_ip(pod) -> tuple[str, str]:
    return pod.metadata.name, pod.status.pod_ip


def get_pods_names_and_ips(pods) -> list[tuple[str, str]]:
    return list(map(lambda pod: get_pod_name_ip(pod), pods))


#### check containers
def is_container_ready(container_name, pod) -> bool:
    result = False
    for cs in pod.status.container_statuses:
        if cs.name == container_name and cs.ready == True:  # Specifies whether the container has passed its readiness probe.
            result = True
    return result


def filter_pods_with_ready_container(pods, container_name):
    return list(filter(lambda pod: is_container_ready(container_name, pod), pods))


#### pod conditions
def check_pod_condition(pod, condition):
    result = False
    if pod.status.conditions:
        for c in pod.status.conditions:
            if c.type == condition and c.status == "True":
                result = True
    return result


def is_pod_ready(pod):
    return check_pod_condition(pod, "Ready")


def filter_ready_pods(pods):
    return list(filter(lambda pod: is_pod_ready(pod), pods))


def get_ready_pods(client: CoreV1Api, app_name, role, namespace, container_name):
    return filter_pods_with_ready_container(
        filter_ready_pods(
            filter_pods_by_label(
                filter_pods_by_label(
                    get_pods_by_namespace(client, namespace),
                    "app",
                    app_name
                ),
                "role",
                role)
        ),
        container_name)


def in_namespace(pod, namespace):
    return pod.metadata.namespace == namespace


class PodMonitor:

    def pod_monitor(self):
        w = watch.Watch()
        exit = False
        while not exit:
            for event in w.stream(self.client.list_pod_for_all_namespaces, timeout_seconds=3):

                if self.stop_event.is_set():
                    exit = True
                    break

                if event['object'].kind == "Pod":
                    pod = event['object']

                    if in_namespace(pod, self.namespace) \
                            and check_pod_label(pod, "app", self.app) \
                            and check_pod_label(pod, "role", self.role):

                        event_t = event['type']

                        global ip_addrs
                        if (event_t == "ADDED" or event_t == "MODIFIED") and is_pod_ready(
                                pod) and pod.status.pod_ip not in self.ip_addrs:
                            self.ip_addrs.append(pod.status.pod_ip)
                            logging.debug(f"Pods activos: {str(self.ip_addrs)}")
                        elif event_t == "DELETED" and pod.status.pod_ip in self.ip_addrs:
                            self.ip_addrs.remove(pod.status.pod_ip)
                            logging.debug(f"Pods activos: {str(self.ip_addrs)}")

                            # print("Event: %s %s %s %s" % (
                        #    event['type'],        #ADDED, MODIFIED, DELETED
                        #    event['object'].kind, #Pod
                        #    event['object'].metadata.name,
                        #    event['object'].status.pod_ip
                        # )
                        # )
                        #print(str(self.ip_addrs))

    def __init__(self, app: str, role: str, namespace: str, client: CoreV1Api):
        self.namespace = namespace
        self.app = app
        self.role = role
        self.client = client
        self.thread = threading.Thread(target=self.pod_monitor)
        self.ip_addrs: list[str] = []
        self.stop_event = threading.Event()

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()

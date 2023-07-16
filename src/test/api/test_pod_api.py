from kubernetes.client import V1ObjectMeta, V1Pod, V1PodList, V1PodStatus, V1PodCondition, V1ContainerStatus

from main.api_groups import pod_api
from main.api_groups.pod_api import PodMonitor
from kubernetes import client, config
import time
class TestPodApi:

    
    def test_pod_monitor(self):
        config.load_kube_config()
        app = "my_app"
        role = "web"
        namespace = "my_namespace"
        cl = client.CoreV1Api()
        pod_monitor = PodMonitor(app, role, namespace, cl)
        pod_monitor.start()
        time.sleep(3)
        pod_monitor.stop()
        assert(len(pod_monitor.ip_addrs) > 0)

    def test_get_pods_by_namespace(self):
        namespace = "my_namespace"
        pods: list[V1Pod] = [pod(namespace=namespace), pod(namespace=namespace), pod(namespace='other')]
        client_stub = CoreApiClientStub(pods)
        res = pod_api.get_pods_by_namespace(client_stub, namespace)
        assert len(res) == 2

    def test_filter_pod_by_label(self):
        app_name = "my_app"
        labels = {"app": app_name}
        pods = [pod(labels=labels), pod(labels=labels), pod(labels={"app": "otra"})]
        res = pod_api.filter_pods_by_label(pods, "app", app_name)
        assert len(res) == 2

    def test_filter_ready_pods(self):
        pods = [pod(), pod(), pod(ready_status=False)]
        res = pod_api.filter_ready_pods(pods)
        assert len(res) == 2

    def test_get_ready_podds(self):
        namespace = "my_namespace"
        labels = {"app": "my_app", "role":"web"}
        containers_readiness = {"web": True, "other": False}
        p1 = pod(namespace=namespace, labels=labels, containers_readiness=containers_readiness)
        p2 = pod(namespace=namespace, labels=labels, containers_readiness=containers_readiness)
        p3 = pod(namespace=namespace, labels=labels, containers_readiness={"web": False, "other": True})
        pods: list[V1Pod] = [p1,p2,p3]
        client_stub = CoreApiClientStub(pods)

        res = pod_api.get_ready_pods(client_stub, "my_app", "web", namespace, container_name="web")
        assert len(res) == 2

class CoreApiClientStub:

    def __init__(self, pl: list[V1Pod]):
        self.pod_list = pl

    def list_pod_for_all_namespaces(self, **kwargs):
        return V1PodList(items=self.pod_list)


def pod(namespace="default", labels=None, ready_status: bool=True, containers_readiness: dict[str,bool]={}):
    if labels is None:
        labels = {}
    p = V1Pod()
    p.metadata = V1ObjectMeta()
    p.metadata.namespace = namespace
    p.metadata.labels = labels
    pod_condition = V1PodCondition(type="Ready", status=str(ready_status))

    css = []

    for c in containers_readiness.keys():
        css.append(V1ContainerStatus(name=c, restart_count=0, ready=containers_readiness[c], image="registro-local:5000/jetty-ex:latest", image_id="feature01"))

    p.status = V1PodStatus(conditions=[pod_condition], container_statuses=css)

    return p

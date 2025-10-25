import os
from dotenv import load_dotenv, find_dotenv
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub

# Load environment variables
load_dotenv(find_dotenv())


def create_pubnub_client():
    """Create and return a configured PubNub instance."""
    pnconfig = PNConfiguration()
    pnconfig.publish_key = os.getenv("PUBNUB_PUBLISH_KEY")
    pnconfig.subscribe_key = os.getenv("PUBNUB_SUBSCRIBE_KEY")
    pnconfig.uuid = "ThermoTrack_Server"
    return PubNub(pnconfig)


# initialize apubnub client for the app
pubnub = create_pubnub_client()

CHANNEL = os.getenv("PUBNUB_CHANNEL", "ThermoTrack")


def publish_data(data: dict):
    """Publish a message (e.g., sensor data) to PubNub."""
    print(f"[PubNub] Publishing to {CHANNEL}: {data}")
    envelope = pubnub.publish().channel(CHANNEL).message(data).sync()
    # check for success or error
    if envelope.status.is_error():
        print(f"[PubNub]  Publish failed: {envelope.status.error_data.information}")
    else:
        print(f"[PubNub]  Message published successfully")


def subscribe_to_updates(callback):
    """Subscribe to PubNub messages and run callback on each."""
    from pubnub.callbacks import SubscribeCallback

    class Listener(SubscribeCallback):
        def message(self, pubnub, message):
            print(f"[PubNub] Message received: {message.message}")
            callback(message.message)

    pubnub.add_listener(Listener())
    pubnub.subscribe().channels(CHANNEL).execute()

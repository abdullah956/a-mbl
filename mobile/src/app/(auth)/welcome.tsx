import { router } from "expo-router";
import React from "react";

import { Banner, Body, Button, Card, Screen, Title } from "../../components/ui";

export default function Welcome() {
  return (
    <Screen>
      <Title>a-mbl</Title>
      <Body>
        A calm space to check hurtful messages. Type or scan a message you received,
        and a-mbl estimates whether it may contain bullying signals — then keeps you
        in control of what is saved or shared.
      </Body>

      <Card>
        <Body muted>
          • Results are automated estimates for your review, never a judgment about a person.{"\n"}
          • Ordinary messages are not kept. Harmful ones are stored encrypted for 30 days.{"\n"}
          • Nothing is shared with a guardian or school unless you choose to share it.
        </Body>
      </Card>

      <Button label="Create an account" onPress={() => router.push("/(auth)/age")} />
      <Button label="I already have an account" kind="secondary"
              onPress={() => router.push("/(auth)/login")} />
      <Button label="Change server address" kind="ghost" onPress={() => router.push("/connect")} />

      <Banner tone="info"
              text="If someone may be in immediate danger, contact a trusted person or an appropriate local service now." />
    </Screen>
  );
}

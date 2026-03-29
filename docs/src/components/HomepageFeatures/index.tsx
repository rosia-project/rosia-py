import type { ReactNode } from "react";
import clsx from "clsx";
import Heading from "@theme/Heading";
import styles from "./styles.module.css";

type FeatureItem = {
  title: string;
  image: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: "Performant",
    image: "/img/features/performant.png",
    description: <>Rosia has more than 2x lower latency compared to ROS2. It also features true concurrency without being blocked by Python's Global Interpreter Lock.</>,
  },
  {
    title: "Reproducible",
    image: "/img/features/deterministic.png",
    description: <>Rosia is reproducible with deterministic execution, allowing you to easily debug and test your robotic applications.</>,
  },
  {
    title: "Component-based",
    image: "/img/features/python.png",
    description: <>Rosia is component-based with ports and connections, allowing you to easily isolate and reuse code.</>,
  },
];

function Feature({ title, image, description }: FeatureItem) {
  return (
    <div className={clsx("col col--4")}>
      <div className="text--center">
        <img className={styles.featureSvg} role="img" src={image} alt={title} />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}

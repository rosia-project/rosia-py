import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  image: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Performance',
    image: require('@site/static/img/features/performant.png').default,
    description: (
      <>
          Rosia is designed from the ground up to be performant and efficient with low latency.
      </>
    ),
  },
  {
    title: 'Deterministic and Reproducible',
    image: require('@site/static/img/features/deterministic.png').default,
    description: (
      <>
        Rosia is deterministic and reproducible, ensuring that the same results are obtained regardless of the runtime.
      </>
    ),
  },
  {
    title: 'Fully Pythonic',
    image: require('@site/static/img/features/python.png').default,
    description: (
      <>
        Rosia is designed to be fully Pythonic, allowing you to use it in your existing Python projects.
      </>
    ),
  },
];

function Feature({title, image, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
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

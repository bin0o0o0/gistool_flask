<script setup lang="ts">
import { ArrowRight, VideoPlay } from '@element-plus/icons-vue'
import SiteNav from '@/components/SiteNav.vue'
import heroBackground from '@/assets/home-water-basin-bg.png'

const featureCards = [
  {
    title: '智能水系提取',
    description: '基于水文拓扑与 DEM 分析，预留河流网络、子流域边界和出口控制点提取流程。',
    icon: '⌁'
  },
  {
    title: '高质量专题出图',
    description: '对接当前 GISTOOL 出图工作台，支持 APRX 模板、站点样式、人工布局和 PNG 导出。',
    icon: '▧'
  }
]
</script>

<template>
  <div class="home-page" :style="{ '--hero-background': `url(${heroBackground})` }">
    <SiteNav />

    <main class="home-hero">
      <section class="home-hero__content" aria-labelledby="home-title">
        <p class="home-hero__kicker">智能水文分析与高质量专题制图平台</p>
        <h1 id="home-title">流域提取 · 可视化出图</h1>
        <p class="home-hero__copy">
          上传 APRX 模板、流域边界、河流与站点 Excel；支持站点逐点样式配置、人工布局控制、自动出图与高质量导出。
        </p>

        <div class="home-hero__actions">
          <RouterLink class="home-button home-button--primary" to="/map-output">
            <span>开始使用</span>
            <el-icon aria-hidden="true"><ArrowRight /></el-icon>
          </RouterLink>
          <a class="home-button home-button--ghost" href="#home-capabilities">
            <el-icon aria-hidden="true"><VideoPlay /></el-icon>
            <span>查看演示</span>
          </a>
        </div>
      </section>

      <section id="home-capabilities" class="capability-strip" aria-label="核心能力">
        <article v-for="card in featureCards" :key="card.title" class="capability-card">
          <span class="capability-card__icon" aria-hidden="true">{{ card.icon }}</span>
          <div>
            <h2>{{ card.title }}</h2>
            <p>{{ card.description }}</p>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>

<style scoped>
.home-page {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(90deg, rgba(2, 11, 29, 0.98) 0%, rgba(2, 11, 29, 0.9) 32%, rgba(2, 11, 29, 0.32) 62%, rgba(2, 11, 29, 0.08) 100%),
    linear-gradient(180deg, rgba(2, 11, 29, 0.2) 0%, rgba(2, 11, 29, 0.16) 58%, rgba(2, 11, 29, 0.9) 100%),
    var(--hero-background) center / cover no-repeat,
    #03162d;
  color: #f4fbff;
}

.home-page::after {
  position: absolute;
  inset: auto 0 0;
  height: 32vh;
  background: linear-gradient(180deg, rgba(2, 12, 28, 0), rgba(2, 12, 28, 0.82));
  content: "";
  pointer-events: none;
}

.home-hero {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(560px, 0.58fr) minmax(360px, 1fr);
  grid-template-rows: minmax(400px, 1fr) auto;
  gap: 28px 40px;
  width: min(100% - 96px, 1760px);
  min-height: calc(100vh - 104px);
  margin: 0 auto;
  padding: clamp(48px, 7vh, 108px) 0 44px;
}

.home-hero__content {
  align-self: center;
  max-width: 840px;
}

.home-hero__kicker {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 24px;
  color: rgba(238, 253, 255, 0.88);
  font-size: 1.3rem;
  font-weight: 800;
  letter-spacing: 0;
}

.home-hero__kicker::before {
  width: 42px;
  height: 1px;
  background: rgba(163, 249, 255, 0.8);
  content: "";
}

.home-hero h1 {
  margin: 0;
  color: #f7fff7;
  font-family: "STKaiti", "KaiTi", "FangSong", var(--font-display);
  font-size: clamp(4rem, 6.2vw, 7.2rem);
  line-height: 1.02;
  letter-spacing: 0;
  text-shadow:
    0 0 18px rgba(106, 244, 240, 0.35),
    0 18px 46px rgba(0, 0, 0, 0.35);
}

.home-hero__copy {
  max-width: 640px;
  margin: 30px 0 0;
  color: rgba(230, 244, 250, 0.84);
  font-size: 1.14rem;
  line-height: 2;
}

.home-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-top: 40px;
}

.home-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-width: 190px;
  min-height: 58px;
  padding: 0 26px;
  border: 1px solid rgba(206, 247, 255, 0.3);
  border-radius: 8px;
  color: #f4fbff;
  font-size: 1.04rem;
  font-weight: 800;
  text-decoration: none;
  transition:
    transform 160ms ease,
    background 160ms ease,
    box-shadow 160ms ease;
}

.home-button:hover {
  transform: translateY(-2px);
}

.home-button--primary {
  border-color: transparent;
  background: linear-gradient(135deg, #91fff5, #31c3e8);
  color: #04233f;
  box-shadow: 0 20px 46px rgba(44, 217, 237, 0.28);
}

.home-button--ghost {
  background: rgba(2, 21, 41, 0.35);
  backdrop-filter: blur(14px);
}

.home-button--ghost:hover {
  background: rgba(255, 255, 255, 0.08);
}

.capability-strip {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 430px));
  gap: 34px;
  align-items: stretch;
  margin-top: 8px;
}

.capability-card {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 24px;
  min-height: 168px;
  padding: 34px;
  border: 1px solid rgba(157, 235, 255, 0.24);
  border-radius: 8px;
  background: rgba(5, 34, 57, 0.48);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px);
}

.capability-card__icon {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(142, 255, 244, 0.28), rgba(53, 178, 238, 0.1));
  color: #a8fff2;
  font-size: 2.35rem;
  font-weight: 800;
}

.capability-card h2,
.capability-card p {
  margin: 0;
}

.capability-card h2 {
  color: #f6fffb;
  font-size: 1.72rem;
  letter-spacing: 0;
}

.capability-card p {
  margin-top: 14px;
  color: rgba(229, 244, 250, 0.82);
  font-size: 1.02rem;
  line-height: 1.85;
}

@media (prefers-reduced-motion: no-preference) {
  .home-hero__content,
  .capability-card {
    animation: home-rise 600ms ease both;
  }

  .capability-card:nth-child(2) {
    animation-delay: 90ms;
  }

}

@keyframes home-rise {
  from {
    opacity: 0;
    transform: translateY(16px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1060px) {
  .home-page {
    background:
      linear-gradient(180deg, rgba(2, 11, 29, 0.94) 0%, rgba(2, 11, 29, 0.72) 48%, rgba(2, 11, 29, 0.94) 100%),
      var(--hero-background) 62% center / cover no-repeat,
      #03162d;
  }

  .home-hero {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto;
    width: min(100% - 48px, 1760px);
    padding-top: 34px;
  }

  .home-hero__content {
    max-width: 760px;
  }

  .capability-strip {
    grid-template-columns: 1fr;
    max-width: 760px;
  }
}

@media (max-width: 720px) {
  .home-page {
    background:
      linear-gradient(180deg, rgba(2, 11, 29, 0.96) 0%, rgba(2, 11, 29, 0.78) 46%, rgba(2, 11, 29, 0.96) 100%),
      var(--hero-background) 58% center / cover no-repeat,
      #03162d;
  }

  .home-hero {
    width: min(100% - 28px, 1760px);
    min-height: auto;
    padding: 28px 0 34px;
  }

  .home-hero__kicker {
    font-size: 1rem;
  }

  .home-hero h1 {
    font-size: clamp(3.3rem, 18vw, 4.8rem);
  }

  .home-hero__copy {
    font-size: 1rem;
    line-height: 1.8;
  }

  .home-hero__actions {
    gap: 12px;
  }

  .home-button {
    flex: 1 1 180px;
    min-width: 0;
  }

  .capability-card {
    grid-template-columns: 1fr;
    gap: 16px;
    padding: 24px;
  }

  .capability-card h2 {
    font-size: 1.35rem;
  }
}
</style>

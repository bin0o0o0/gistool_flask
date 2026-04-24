<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'

const navItems = [
  { label: '首页', to: '/' },
  { label: '流域提取', to: '/watershed-extract' },
  { label: '流域出图', to: '/map-output' },
  { label: '使用指南', to: '/guide' }
]
</script>

<template>
  <header class="site-nav">
    <RouterLink class="site-brand" to="/" aria-label="返回首页">
      <span class="site-brand__mark" aria-hidden="true">
        <span></span>
      </span>
      <span>
        <strong>GISTOOL / 流域工具</strong>
        <small>流域提取与专题出图平台</small>
      </span>
    </RouterLink>

    <nav class="site-nav__links" aria-label="主导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="site-nav__link"
      >
        {{ item.label }}
      </RouterLink>
    </nav>

    <RouterLink class="site-nav__action" to="/map-output">
      <span>开始使用</span>
      <el-icon aria-hidden="true"><ArrowRight /></el-icon>
    </RouterLink>
  </header>
</template>

<style scoped>
.site-nav {
  position: relative;
  z-index: 10;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto minmax(160px, 1fr);
  gap: 24px;
  align-items: center;
  width: min(100% - 64px, 1760px);
  margin: 0 auto;
  padding: 24px 0;
}

.site-brand,
.site-nav__link,
.site-nav__action {
  color: inherit;
  text-decoration: none;
}

.site-brand {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  width: fit-content;
  color: #d8fff6;
}

.site-brand__mark {
  position: relative;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border: 1px solid rgba(120, 242, 228, 0.34);
  border-radius: 8px;
  background:
    linear-gradient(145deg, rgba(118, 236, 224, 0.22), rgba(24, 133, 177, 0.08)),
    rgba(4, 27, 48, 0.62);
  box-shadow: 0 16px 36px rgba(0, 201, 255, 0.18);
}

.site-brand__mark span {
  width: 23px;
  height: 28px;
  clip-path: polygon(50% 0, 100% 84%, 50% 66%, 0 84%);
  background: linear-gradient(180deg, #a8fff2, #24c8e5);
}

.site-brand strong,
.site-brand small {
  display: block;
  letter-spacing: 0;
}

.site-brand strong {
  font-size: 1.5rem;
  line-height: 1.1;
}

.site-brand small {
  margin-top: 5px;
  color: rgba(218, 244, 255, 0.72);
  font-size: 0.84rem;
}

.site-nav__links {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: min(100%, 760px);
  padding: 7px;
  border: 1px solid rgba(187, 238, 255, 0.12);
  border-radius: 8px;
  background: rgba(4, 24, 45, 0.42);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(18px);
}

.site-nav__link {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 124px;
  height: 42px;
  padding: 0 18px;
  border-radius: 7px;
  color: rgba(236, 250, 255, 0.78);
  font-weight: 700;
  transition:
    color 160ms ease,
    background 160ms ease;
}

.site-nav__link:hover,
.site-nav__link.router-link-exact-active {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.07);
}

.site-nav__link.router-link-exact-active::after {
  position: absolute;
  bottom: -8px;
  left: 50%;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #73fff0;
  box-shadow: 0 0 20px rgba(115, 255, 240, 0.9);
  content: "";
  transform: translateX(-50%);
}

.site-nav__action {
  display: inline-flex;
  align-items: center;
  justify-self: end;
  gap: 10px;
  min-height: 48px;
  padding: 0 24px;
  border-radius: 8px;
  background: linear-gradient(135deg, #8dfff3, #3bc9ee);
  color: #04233f;
  font-weight: 800;
  box-shadow: 0 18px 46px rgba(45, 219, 240, 0.22);
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}

.site-nav__action:hover {
  transform: translateY(-1px);
  box-shadow: 0 22px 56px rgba(45, 219, 240, 0.3);
}

@media (max-width: 1160px) {
  .site-nav {
    grid-template-columns: 1fr auto;
  }

  .site-nav__links {
    grid-column: 1 / -1;
    grid-row: 2;
    justify-content: flex-start;
    overflow-x: auto;
  }
}

@media (max-width: 720px) {
  .site-nav {
    width: min(100% - 28px, 1760px);
    gap: 14px;
    padding-top: 16px;
  }

  .site-brand__mark {
    width: 42px;
    height: 42px;
  }

  .site-brand strong {
    font-size: 1.08rem;
  }

  .site-brand small {
    display: none;
  }

  .site-nav__action {
    min-height: 42px;
    padding: 0 14px;
  }

  .site-nav__action span {
    display: none;
  }

  .site-nav__links {
    width: 100%;
    padding: 6px;
  }

  .site-nav__link {
    min-width: 92px;
    height: 38px;
    padding: 0 12px;
    font-size: 0.92rem;
  }
}
</style>
